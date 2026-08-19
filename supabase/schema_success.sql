-- Additive Student Success / Risk / Intervention layer.
-- Does NOT alter teachers, students, subjects, subject_students, attendance_logs,
-- face embeddings, or voice embeddings.

create table if not exists public.staff_users (
  staff_id bigserial primary key,
  username text not null unique,
  password text not null,
  name text not null,
  role text not null check (role in ('administrator','counsellor','faculty','mentor')),
  created_at timestamptz not null default now()
);

create table if not exists public.staff_invites (
  invite_id bigserial primary key,
  invited_name text not null,
  invited_username text not null,
  assigned_role text not null,
  token_hash text not null,
  invited_by text,
  expires_at timestamptz not null,
  used_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.academic_records (
  id bigserial primary key,
  student_id bigint not null references public.students(student_id) on delete cascade,
  subject_id bigint references public.subjects(subject_id) on delete set null,
  semester text,
  assessment text,
  score numeric,
  max_score numeric,
  gpa numeric,
  backlog boolean not null default false,
  recorded_at timestamptz not null default now()
);

create table if not exists public.lms_events (
  id bigserial primary key,
  student_id bigint not null references public.students(student_id) on delete cascade,
  event_type text not null,
  course_code text,
  occurred_at timestamptz not null default now()
);

create table if not exists public.student_context (
  student_id bigint primary key references public.students(student_id) on delete cascade,
  workload_note text,
  digital_access text,
  self_report text,
  minimized boolean not null default true,
  updated_at timestamptz not null default now()
);

create table if not exists public.risk_predictions (
  id bigserial primary key,
  student_id bigint not null references public.students(student_id) on delete cascade,
  score numeric not null,
  category text not null,
  probability numeric,
  confidence numeric,
  velocity numeric,
  missing_data boolean not null default false,
  model_version text not null default 'success-risk-v1',
  explanation jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.alerts (
  id bigserial primary key,
  student_id bigint references public.students(student_id) on delete cascade,
  source text not null,
  severity text not null,
  title text not null,
  status text not null default 'open',
  owner text,
  created_at timestamptz not null default now(),
  resolved_at timestamptz
);

create table if not exists public.intervention_library (
  id bigserial primary key,
  name text not null,
  domain text not null,
  owner_role text,
  available boolean not null default true,
  success_criteria text,
  created_at timestamptz not null default now()
);

create table if not exists public.intervention_cases (
  id bigserial primary key,
  case_code text not null unique,
  student_id bigint not null references public.students(student_id) on delete cascade,
  owner text,
  priority text not null default 'medium',
  status text not null default 'open',
  intervention_name text,
  deadline timestamptz,
  notes text,
  created_at timestamptz not null default now(),
  closed_at timestamptz,
  closure_reason text
);

create table if not exists public.intervention_recommendations (
  id bigserial primary key,
  student_id bigint not null references public.students(student_id) on delete cascade,
  recommendation text not null,
  reason text,
  confidence numeric,
  status text not null default 'pending',
  reviewer text,
  reviewer_note text,
  created_at timestamptz not null default now()
);

create table if not exists public.intervention_outcomes (
  id bigserial primary key,
  case_id bigint references public.intervention_cases(id) on delete cascade,
  classification text not null,
  notes text,
  recorded_by text,
  created_at timestamptz not null default now()
);

create table if not exists public.recovery_plans (
  id bigserial primary key,
  student_id bigint not null references public.students(student_id) on delete cascade,
  title text not null,
  weekly_plan text,
  created_by text,
  created_at timestamptz not null default now()
);

create table if not exists public.recovery_tasks (
  id bigserial primary key,
  plan_id bigint references public.recovery_plans(id) on delete cascade,
  student_id bigint not null references public.students(student_id) on delete cascade,
  task text not null,
  done boolean not null default false
);

create table if not exists public.notifications (
  id bigserial primary key,
  recipient_role text,
  recipient_id text,
  title text not null,
  body text,
  created_at timestamptz not null default now(),
  read_at timestamptz
);

create table if not exists public.messages (
  id bigserial primary key,
  sender text,
  recipient text,
  channel text not null default 'in_app',
  body text not null,
  status text not null default 'queued',
  created_at timestamptz not null default now()
);

create table if not exists public.appointments (
  id bigserial primary key,
  student_id bigint references public.students(student_id) on delete cascade,
  staff_name text,
  kind text,
  starts_at timestamptz,
  status text not null default 'requested',
  notes text
);

create table if not exists public.audit_events (
  id bigserial primary key,
  actor text,
  action text not null,
  entity text,
  detail text,
  created_at timestamptz not null default now()
);

create table if not exists public.import_jobs (
  id bigserial primary key,
  kind text not null,
  filename text,
  status text not null,
  summary text,
  created_at timestamptz not null default now()
);

create table if not exists public.institution_settings (
  id int primary key default 1,
  settings jsonb not null default '{}'::jsonb
);

alter table public.staff_users enable row level security;
alter table public.staff_invites enable row level security;
alter table public.academic_records enable row level security;
alter table public.lms_events enable row level security;
alter table public.student_context enable row level security;
alter table public.risk_predictions enable row level security;
alter table public.alerts enable row level security;
alter table public.intervention_library enable row level security;
alter table public.intervention_cases enable row level security;
alter table public.intervention_recommendations enable row level security;
alter table public.intervention_outcomes enable row level security;
alter table public.recovery_plans enable row level security;
alter table public.recovery_tasks enable row level security;
alter table public.notifications enable row level security;
alter table public.messages enable row level security;
alter table public.appointments enable row level security;
alter table public.audit_events enable row level security;
alter table public.import_jobs enable row level security;
alter table public.institution_settings enable row level security;

drop policy if exists "anon_all_staff_users" on public.staff_users;
drop policy if exists "anon_all_staff_invites" on public.staff_invites;
drop policy if exists "anon_all_academic_records" on public.academic_records;
drop policy if exists "anon_all_lms_events" on public.lms_events;
drop policy if exists "anon_all_student_context" on public.student_context;
drop policy if exists "anon_all_risk_predictions" on public.risk_predictions;
drop policy if exists "anon_all_alerts" on public.alerts;
drop policy if exists "anon_all_intervention_library" on public.intervention_library;
drop policy if exists "anon_all_intervention_cases" on public.intervention_cases;
drop policy if exists "anon_all_intervention_recommendations" on public.intervention_recommendations;
drop policy if exists "anon_all_intervention_outcomes" on public.intervention_outcomes;
drop policy if exists "anon_all_recovery_plans" on public.recovery_plans;
drop policy if exists "anon_all_recovery_tasks" on public.recovery_tasks;
drop policy if exists "anon_all_notifications" on public.notifications;
drop policy if exists "anon_all_messages" on public.messages;
drop policy if exists "anon_all_appointments" on public.appointments;
drop policy if exists "anon_all_audit_events" on public.audit_events;
drop policy if exists "anon_all_import_jobs" on public.import_jobs;
drop policy if exists "anon_all_institution_settings" on public.institution_settings;

create policy "anon_all_staff_users" on public.staff_users for all to anon, authenticated using (true) with check (true);
create policy "anon_all_staff_invites" on public.staff_invites for all to anon, authenticated using (true) with check (true);
create policy "anon_all_academic_records" on public.academic_records for all to anon, authenticated using (true) with check (true);
create policy "anon_all_lms_events" on public.lms_events for all to anon, authenticated using (true) with check (true);
create policy "anon_all_student_context" on public.student_context for all to anon, authenticated using (true) with check (true);
create policy "anon_all_risk_predictions" on public.risk_predictions for all to anon, authenticated using (true) with check (true);
create policy "anon_all_alerts" on public.alerts for all to anon, authenticated using (true) with check (true);
create policy "anon_all_intervention_library" on public.intervention_library for all to anon, authenticated using (true) with check (true);
create policy "anon_all_intervention_cases" on public.intervention_cases for all to anon, authenticated using (true) with check (true);
create policy "anon_all_intervention_recommendations" on public.intervention_recommendations for all to anon, authenticated using (true) with check (true);
create policy "anon_all_intervention_outcomes" on public.intervention_outcomes for all to anon, authenticated using (true) with check (true);
create policy "anon_all_recovery_plans" on public.recovery_plans for all to anon, authenticated using (true) with check (true);
create policy "anon_all_recovery_tasks" on public.recovery_tasks for all to anon, authenticated using (true) with check (true);
create policy "anon_all_notifications" on public.notifications for all to anon, authenticated using (true) with check (true);
create policy "anon_all_messages" on public.messages for all to anon, authenticated using (true) with check (true);
create policy "anon_all_appointments" on public.appointments for all to anon, authenticated using (true) with check (true);
create policy "anon_all_audit_events" on public.audit_events for all to anon, authenticated using (true) with check (true);
create policy "anon_all_import_jobs" on public.import_jobs for all to anon, authenticated using (true) with check (true);
create policy "anon_all_institution_settings" on public.institution_settings for all to anon, authenticated using (true) with check (true);

notify pgrst, 'reload schema';

