-- Additive secure multi-layer attendance.
-- Does NOT alter attendance_logs, students, subjects, or face/voice columns.
-- Final PRESENT still writes a normal attendance_logs row so existing analytics keep working.

create table if not exists public.secure_attendance_settings (
  id int primary key default 1,
  settings jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.attendance_sessions (
  id bigserial primary key,
  institution_id text not null default 'default',
  public_id text not null unique,
  subject_id bigint not null,
  subject_code text,
  subject_name text,
  section text,
  teacher_id bigint not null,
  teacher_name text,
  lecture text,
  status text not null,
  verification_mode text not null,
  started_at timestamptz not null default now(),
  expires_at timestamptz not null,
  completed_at timestamptz,
  cancel_reason text,
  created_at timestamptz not null default now()
);

create table if not exists public.attendance_face_results (
  id bigserial primary key,
  institution_id text not null default 'default',
  session_id bigint not null references public.attendance_sessions(id) on delete cascade,
  session_public_id text,
  student_id bigint,
  confidence numeric,
  distance numeric,
  recognition_status text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.attendance_marks (
  id bigserial primary key,
  institution_id text not null default 'default',
  session_id bigint not null references public.attendance_sessions(id) on delete cascade,
  session_public_id text,
  student_id bigint not null,
  student_name text,
  status text not null,
  face_status text,
  confidence numeric,
  verification_method text,
  source text,
  verified_at timestamptz,
  verified_by text,
  review_reason text,
  created_at timestamptz not null default now(),
  unique (session_id, student_id)
);

create table if not exists public.attendance_tokens (
  id bigserial primary key,
  institution_id text not null default 'default',
  session_id bigint not null references public.attendance_sessions(id) on delete cascade,
  session_public_id text,
  student_id bigint not null,
  kind text not null,
  token_hash text not null,
  token_hint text,
  status text not null,
  expires_at timestamptz,
  used_at timestamptz,
  hold_code text,
  created_at timestamptz not null default now()
);

create table if not exists public.attendance_devices (
  id bigserial primary key,
  institution_id text not null default 'default',
  student_id bigint not null,
  secret_hash text not null,
  status text not null default 'ACTIVE',
  registered_at timestamptz not null default now(),
  last_used_at timestamptz
);

create table if not exists public.attendance_audit (
  id bigserial primary key,
  institution_id text not null default 'default',
  actor text,
  actor_role text,
  action text not null,
  attendance_session_id text,
  student_id bigint,
  previous_state text,
  new_state text,
  reason text,
  created_at timestamptz not null default now()
);

create table if not exists public.attendance_disputes (
  id bigserial primary key,
  institution_id text not null default 'default',
  session_id bigint,
  session_public_id text,
  student_id bigint not null,
  reason text not null,
  status text not null default 'OPEN',
  created_at timestamptz not null default now()
);

create index if not exists idx_att_sess_teacher on public.attendance_sessions(teacher_id);
create index if not exists idx_att_sess_public on public.attendance_sessions(public_id);
create index if not exists idx_att_mark_session on public.attendance_marks(session_id);
create index if not exists idx_att_mark_student on public.attendance_marks(student_id);
create index if not exists idx_att_tok_hash on public.attendance_tokens(token_hash);
create index if not exists idx_att_tok_student on public.attendance_tokens(student_id);
create index if not exists idx_att_dev_student on public.attendance_devices(student_id);

alter table public.secure_attendance_settings enable row level security;
alter table public.attendance_sessions enable row level security;
alter table public.attendance_face_results enable row level security;
alter table public.attendance_marks enable row level security;
alter table public.attendance_tokens enable row level security;
alter table public.attendance_devices enable row level security;
alter table public.attendance_audit enable row level security;
alter table public.attendance_disputes enable row level security;

drop policy if exists "anon_all_secure_attendance_settings" on public.secure_attendance_settings;
drop policy if exists "anon_all_attendance_sessions" on public.attendance_sessions;
drop policy if exists "anon_all_attendance_face_results" on public.attendance_face_results;
drop policy if exists "anon_all_attendance_marks" on public.attendance_marks;
drop policy if exists "anon_all_attendance_tokens" on public.attendance_tokens;
drop policy if exists "anon_all_attendance_devices" on public.attendance_devices;
drop policy if exists "anon_all_attendance_audit" on public.attendance_audit;
drop policy if exists "anon_all_attendance_disputes" on public.attendance_disputes;

create policy "anon_all_secure_attendance_settings" on public.secure_attendance_settings for all to anon, authenticated using (true) with check (true);
create policy "anon_all_attendance_sessions" on public.attendance_sessions for all to anon, authenticated using (true) with check (true);
create policy "anon_all_attendance_face_results" on public.attendance_face_results for all to anon, authenticated using (true) with check (true);
create policy "anon_all_attendance_marks" on public.attendance_marks for all to anon, authenticated using (true) with check (true);
create policy "anon_all_attendance_tokens" on public.attendance_tokens for all to anon, authenticated using (true) with check (true);
create policy "anon_all_attendance_devices" on public.attendance_devices for all to anon, authenticated using (true) with check (true);
create policy "anon_all_attendance_audit" on public.attendance_audit for all to anon, authenticated using (true) with check (true);
create policy "anon_all_attendance_disputes" on public.attendance_disputes for all to anon, authenticated using (true) with check (true);

notify pgrst, 'reload schema';
