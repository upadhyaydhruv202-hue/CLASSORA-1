-- Additive Anonymous Counseling & Mentorship layer.
-- Does NOT alter teachers, students, subjects, attendance, face/voice embeddings,
-- or existing success-hub tables.

create table if not exists public.mentor_profiles (
  staff_id bigint primary key references public.staff_users(staff_id) on delete cascade,
  expertise text,
  available boolean not null default true,
  max_caseload int not null default 6,
  updated_at timestamptz not null default now()
);

create table if not exists public.mentorships (
  mentorship_id uuid primary key default gen_random_uuid(),
  student_id bigint not null references public.students(student_id) on delete cascade,
  mentor_staff_id bigint not null references public.staff_users(staff_id) on delete restrict,
  student_alias text not null unique,
  mentor_alias text not null unique,
  status text not null check (status in (
    'ASSIGNED',
    'ANONYMOUS_ACTIVE',
    'FEEDBACK_PENDING',
    'ACCEPTED',
    'IDENTITIES_REVEALED',
    'REJECTED',
    'REASSIGNMENT_PENDING',
    'COMPLETED',
    'SUSPENDED'
  )),
  counseling_goal text,
  risk_band text,
  attendance_context text,
  started_at timestamptz not null default now(),
  feedback_due_at timestamptz not null,
  revealed_at timestamptz,
  closed_at timestamptz,
  previous_mentorship_id uuid references public.mentorships(mentorship_id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists mentorships_one_open_per_student
  on public.mentorships (student_id)
  where status in ('ASSIGNED', 'ANONYMOUS_ACTIVE', 'FEEDBACK_PENDING', 'REASSIGNMENT_PENDING');

create index if not exists mentorships_mentor_status on public.mentorships (mentor_staff_id, status);
create index if not exists mentorships_student_status on public.mentorships (student_id, status);
create index if not exists mentorships_feedback_due on public.mentorships (feedback_due_at);

create table if not exists public.anonymous_profiles (
  alias text primary key,
  mentorship_id uuid not null references public.mentorships(mentorship_id) on delete cascade,
  party text not null check (party in ('student', 'mentor')),
  created_at timestamptz not null default now()
);

create table if not exists public.mentor_assignments (
  id bigserial primary key,
  mentorship_id uuid references public.mentorships(mentorship_id) on delete set null,
  student_id bigint not null references public.students(student_id) on delete cascade,
  mentor_staff_id bigint not null references public.staff_users(staff_id) on delete cascade,
  outcome text not null check (outcome in ('assigned', 'rejected', 'accepted', 'reassigned', 'suspended')),
  created_at timestamptz not null default now()
);

create index if not exists mentor_assignments_pair on public.mentor_assignments (student_id, mentor_staff_id);

create table if not exists public.mentorship_sessions (
  id bigserial primary key,
  mentorship_id uuid not null references public.mentorships(mentorship_id) on delete cascade,
  title text,
  notes text,
  created_by_role text not null check (created_by_role in ('student', 'mentor')),
  created_at timestamptz not null default now()
);

create table if not exists public.mentorship_messages (
  id bigserial primary key,
  mentorship_id uuid not null references public.mentorships(mentorship_id) on delete cascade,
  sender_role text not null check (sender_role in ('student', 'mentor')),
  body text not null,
  created_at timestamptz not null default now()
);

create index if not exists mentorship_messages_thread on public.mentorship_messages (mentorship_id, created_at);

create table if not exists public.mentorship_feedback (
  id bigserial primary key,
  mentorship_id uuid not null references public.mentorships(mentorship_id) on delete cascade,
  student_id bigint not null references public.students(student_id) on delete cascade,
  satisfaction int not null check (satisfaction between 1 and 5),
  mentor_helpful boolean,
  felt_comfortable boolean,
  understood_concerns boolean,
  counseling_helped boolean,
  want_to_continue boolean not null,
  written_feedback text,
  created_at timestamptz not null default now(),
  unique (mentorship_id)
);

create table if not exists public.identity_reveals (
  id bigserial primary key,
  mentorship_id uuid not null unique references public.mentorships(mentorship_id) on delete cascade,
  revealed_by_student_id bigint not null references public.students(student_id) on delete cascade,
  revealed_at timestamptz not null default now(),
  irreversible boolean not null default true
);

create table if not exists public.mentorship_notifications (
  id bigserial primary key,
  recipient_role text not null check (recipient_role in ('student', 'mentor', 'administrator', 'counsellor')),
  recipient_student_id bigint references public.students(student_id) on delete cascade,
  recipient_staff_id bigint references public.staff_users(staff_id) on delete cascade,
  title text not null,
  body text not null,
  mentorship_id uuid references public.mentorships(mentorship_id) on delete cascade,
  read_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.mentorship_audit_logs (
  id bigserial primary key,
  actor_role text,
  actor_ref text,
  action text not null,
  mentorship_id uuid,
  detail text,
  created_at timestamptz not null default now()
);

alter table public.mentor_profiles enable row level security;
alter table public.mentorships enable row level security;
alter table public.anonymous_profiles enable row level security;
alter table public.mentor_assignments enable row level security;
alter table public.mentorship_sessions enable row level security;
alter table public.mentorship_messages enable row level security;
alter table public.mentorship_feedback enable row level security;
alter table public.identity_reveals enable row level security;
alter table public.mentorship_notifications enable row level security;
alter table public.mentorship_audit_logs enable row level security;

drop policy if exists "anon_all_mentor_profiles" on public.mentor_profiles;
drop policy if exists "anon_all_mentorships" on public.mentorships;
drop policy if exists "anon_all_anonymous_profiles" on public.anonymous_profiles;
drop policy if exists "anon_all_mentor_assignments" on public.mentor_assignments;
drop policy if exists "anon_all_mentorship_sessions" on public.mentorship_sessions;
drop policy if exists "anon_all_mentorship_messages" on public.mentorship_messages;
drop policy if exists "anon_all_mentorship_feedback" on public.mentorship_feedback;
drop policy if exists "anon_all_identity_reveals" on public.identity_reveals;
drop policy if exists "anon_all_mentorship_notifications" on public.mentorship_notifications;
drop policy if exists "anon_all_mentorship_audit_logs" on public.mentorship_audit_logs;

-- Streamlit uses the anon key. Identity is enforced in the Python service layer:
-- queries never return student_id / mentor_staff_id / names until IDENTITIES_REVEALED.
create policy "anon_all_mentor_profiles" on public.mentor_profiles for all to anon, authenticated using (true) with check (true);
create policy "anon_all_mentorships" on public.mentorships for all to anon, authenticated using (true) with check (true);
create policy "anon_all_anonymous_profiles" on public.anonymous_profiles for all to anon, authenticated using (true) with check (true);
create policy "anon_all_mentor_assignments" on public.mentor_assignments for all to anon, authenticated using (true) with check (true);
create policy "anon_all_mentorship_sessions" on public.mentorship_sessions for all to anon, authenticated using (true) with check (true);
create policy "anon_all_mentorship_messages" on public.mentorship_messages for all to anon, authenticated using (true) with check (true);
create policy "anon_all_mentorship_feedback" on public.mentorship_feedback for all to anon, authenticated using (true) with check (true);
create policy "anon_all_identity_reveals" on public.identity_reveals for all to anon, authenticated using (true) with check (true);
create policy "anon_all_mentorship_notifications" on public.mentorship_notifications for all to anon, authenticated using (true) with check (true);
create policy "anon_all_mentorship_audit_logs" on public.mentorship_audit_logs for all to anon, authenticated using (true) with check (true);

notify pgrst, 'reload schema';
