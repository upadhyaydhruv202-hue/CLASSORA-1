-- SnapClass schema for Supabase
-- Run this in: Supabase Dashboard → SQL Editor → New query → Run

-- Teachers
create table if not exists public.teachers (
  teacher_id bigserial primary key,
  username text not null unique,
  password text not null,
  name text not null,
  created_at timestamptz not null default now()
);

-- Students (face/voice embeddings stored as JSON arrays)
create table if not exists public.students (
  student_id bigserial primary key,
  name text not null,
  face_embedding jsonb,
  voice_embedding jsonb,
  created_at timestamptz not null default now()
);

-- Subjects
create table if not exists public.subjects (
  subject_id bigserial primary key,
  subject_code text not null unique,
  name text not null,
  section text not null,
  teacher_id bigint not null references public.teachers(teacher_id) on delete cascade,
  created_at timestamptz not null default now()
);

-- Enrollment
create table if not exists public.subject_students (
  id bigserial primary key,
  student_id bigint not null references public.students(student_id) on delete cascade,
  subject_id bigint not null references public.subjects(subject_id) on delete cascade,
  created_at timestamptz not null default now(),
  unique (student_id, subject_id)
);

-- Attendance logs
create table if not exists public.attendance_logs (
  id bigserial primary key,
  student_id bigint not null references public.students(student_id) on delete cascade,
  subject_id bigint not null references public.subjects(subject_id) on delete cascade,
  timestamp timestamptz not null default now(),
  is_present boolean not null default false
);

-- Indexes for common lookups
create index if not exists idx_subjects_teacher_id on public.subjects(teacher_id);
create index if not exists idx_subject_students_subject_id on public.subject_students(subject_id);
create index if not exists idx_subject_students_student_id on public.subject_students(student_id);
create index if not exists idx_attendance_logs_subject_id on public.attendance_logs(subject_id);
create index if not exists idx_attendance_logs_student_id on public.attendance_logs(student_id);

-- App uses the anon key for all reads/writes (student project style).
-- Enable open policies so the Streamlit client can operate.
alter table public.teachers enable row level security;
alter table public.students enable row level security;
alter table public.subjects enable row level security;
alter table public.subject_students enable row level security;
alter table public.attendance_logs enable row level security;

drop policy if exists "anon_all_teachers" on public.teachers;
drop policy if exists "anon_all_students" on public.students;
drop policy if exists "anon_all_subjects" on public.subjects;
drop policy if exists "anon_all_subject_students" on public.subject_students;
drop policy if exists "anon_all_attendance_logs" on public.attendance_logs;

create policy "anon_all_teachers" on public.teachers for all to anon, authenticated using (true) with check (true);
create policy "anon_all_students" on public.students for all to anon, authenticated using (true) with check (true);
create policy "anon_all_subjects" on public.subjects for all to anon, authenticated using (true) with check (true);
create policy "anon_all_subject_students" on public.subject_students for all to anon, authenticated using (true) with check (true);
create policy "anon_all_attendance_logs" on public.attendance_logs for all to anon, authenticated using (true) with check (true);

-- Additive auth tables (safe to re-run). See also supabase/schema_auth.sql
create table if not exists public.auth_events (
  id bigserial primary key,
  username text,
  role text,
  event text not null,
  status text not null default 'ok',
  created_at timestamptz not null default now()
);

create table if not exists public.teacher_invites (
  invite_id bigserial primary key,
  invited_name text not null,
  invited_username text not null,
  token_hash text not null,
  invited_by bigint references public.teachers(teacher_id) on delete set null,
  expires_at timestamptz not null,
  used_at timestamptz,
  created_at timestamptz not null default now()
);

alter table public.auth_events enable row level security;
alter table public.teacher_invites enable row level security;

drop policy if exists "anon_all_auth_events" on public.auth_events;
drop policy if exists "anon_all_teacher_invites" on public.teacher_invites;
create policy "anon_all_auth_events" on public.auth_events for all to anon, authenticated using (true) with check (true);
create policy "anon_all_teacher_invites" on public.teacher_invites for all to anon, authenticated using (true) with check (true);

notify pgrst, 'reload schema';
