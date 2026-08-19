-- Additive misconduct complaint + admin-only ban layer.
-- Run AFTER supabase/schema_mentorship.sql (mentorships FK).
-- Does not alter face/voice pipelines, attendance tables, or drop existing records.

create table if not exists public.student_moderation_status (
  student_id bigint primary key references public.students(student_id) on delete cascade,
  status text not null check (status in ('ACTIVE', 'RESTRICTED', 'SUSPENDED', 'BANNED')),
  until_at timestamptz,
  reason text,
  updated_by_staff_id bigint references public.staff_users(staff_id) on delete set null,
  updated_at timestamptz not null default now()
);

create table if not exists public.complaints (
  complaint_id uuid primary key default gen_random_uuid(),
  complaint_code text not null unique,
  reporter_staff_id bigint references public.staff_users(staff_id) on delete restrict,
  reporter_teacher_id bigint references public.teachers(teacher_id) on delete restrict,
  student_id bigint not null references public.students(student_id) on delete restrict,
  mentorship_id uuid references public.mentorships(mentorship_id) on delete set null,
  student_alias_snapshot text,
  category text not null,
  severity text not null check (severity in ('low', 'medium', 'high', 'critical')),
  incident_at timestamptz,
  description text not null,
  requested_action text not null check (requested_action in ('warning', 'review', 'temporary_restriction', 'student_id_ban')),
  status text not null check (status in (
    'SUBMITTED',
    'UNDER_REVIEW',
    'INFO_REQUIRED',
    'DISMISSED',
    'ACTION_REQUIRED',
    'WARNING_ISSUED',
    'RESTRICTED',
    'BANNED'
  )),
  has_evidence boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint complaints_has_reporter check (reporter_staff_id is not null or reporter_teacher_id is not null)
);

create index if not exists complaints_status_idx on public.complaints (status, created_at desc);
create index if not exists complaints_student_idx on public.complaints (student_id);
create index if not exists complaints_reporter_idx on public.complaints (reporter_staff_id);
create index if not exists complaints_teacher_idx on public.complaints (reporter_teacher_id);

create table if not exists public.complaint_evidence (
  id bigserial primary key,
  complaint_id uuid not null references public.complaints(complaint_id) on delete cascade,
  filename text,
  mime text,
  byte_size int,
  sha256 text,
  note text,
  added_by_role text not null,
  added_by_ref text,
  created_at timestamptz not null default now()
);

create table if not exists public.complaint_reviews (
  id bigserial primary key,
  complaint_id uuid not null references public.complaints(complaint_id) on delete cascade,
  admin_staff_id bigint not null references public.staff_users(staff_id) on delete restrict,
  decision text not null,
  reason text,
  created_at timestamptz not null default now()
);

create table if not exists public.complaint_messages (
  id bigserial primary key,
  complaint_id uuid not null references public.complaints(complaint_id) on delete cascade,
  author_role text not null check (author_role in ('faculty', 'administrator')),
  body text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.moderation_actions (
  id bigserial primary key,
  complaint_id uuid references public.complaints(complaint_id) on delete set null,
  student_id bigint not null references public.students(student_id) on delete cascade,
  admin_staff_id bigint not null references public.staff_users(staff_id) on delete restrict,
  action text not null check (action in ('dismiss', 'warning', 'restrict', 'suspend', 'ban', 'restore', 'reduce')),
  duration_hours int,
  reason text,
  created_at timestamptz not null default now()
);

create table if not exists public.student_appeals (
  id bigserial primary key,
  student_id bigint not null references public.students(student_id) on delete cascade,
  complaint_id uuid references public.complaints(complaint_id) on delete set null,
  reason text not null,
  explanation text,
  evidence_note text,
  status text not null check (status in ('SUBMITTED', 'ACCEPTED', 'REJECTED')) default 'SUBMITTED',
  admin_note text,
  created_at timestamptz not null default now(),
  reviewed_at timestamptz
);

create table if not exists public.moderation_audit_logs (
  id bigserial primary key,
  actor_role text,
  actor_ref text,
  action text not null,
  complaint_id uuid,
  student_id bigint,
  previous_status text,
  new_status text,
  reason text,
  metadata text,
  created_at timestamptz not null default now()
);

alter table public.student_moderation_status enable row level security;
alter table public.complaints enable row level security;
alter table public.complaint_evidence enable row level security;
alter table public.complaint_reviews enable row level security;
alter table public.complaint_messages enable row level security;
alter table public.moderation_actions enable row level security;
alter table public.student_appeals enable row level security;
alter table public.moderation_audit_logs enable row level security;

drop policy if exists "anon_all_student_moderation_status" on public.student_moderation_status;
drop policy if exists "anon_all_complaints" on public.complaints;
drop policy if exists "anon_all_complaint_evidence" on public.complaint_evidence;
drop policy if exists "anon_all_complaint_reviews" on public.complaint_reviews;
drop policy if exists "anon_all_complaint_messages" on public.complaint_messages;
drop policy if exists "anon_all_moderation_actions" on public.moderation_actions;
drop policy if exists "anon_all_student_appeals" on public.student_appeals;
drop policy if exists "anon_all_moderation_audit_logs" on public.moderation_audit_logs;

-- Streamlit anon key: authorization is enforced in src/moderation/service.py
create policy "anon_all_student_moderation_status" on public.student_moderation_status for all to anon, authenticated using (true) with check (true);
create policy "anon_all_complaints" on public.complaints for all to anon, authenticated using (true) with check (true);
create policy "anon_all_complaint_evidence" on public.complaint_evidence for all to anon, authenticated using (true) with check (true);
create policy "anon_all_complaint_reviews" on public.complaint_reviews for all to anon, authenticated using (true) with check (true);
create policy "anon_all_complaint_messages" on public.complaint_messages for all to anon, authenticated using (true) with check (true);
create policy "anon_all_moderation_actions" on public.moderation_actions for all to anon, authenticated using (true) with check (true);
create policy "anon_all_student_appeals" on public.student_appeals for all to anon, authenticated using (true) with check (true);
create policy "anon_all_moderation_audit_logs" on public.moderation_audit_logs for all to anon, authenticated using (true) with check (true);

notify pgrst, 'reload schema';
