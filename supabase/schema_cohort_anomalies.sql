-- Additive Institutional Cohort Anomaly Detection.
-- Does NOT alter students, teachers, subjects, attendance, risk, mentorship, or academic resources.

create table if not exists public.institutional_anomalies (
  id bigserial primary key,
  institution_id text not null default 'default',
  event_key text not null,
  identity_key text not null,
  parent_id bigint references public.institutional_anomalies(id) on delete set null,
  cohort_type text not null,
  cohort_key text not null,
  cohort_label text not null,
  section text,
  subject_id bigint,
  subject_name text,
  subject_code text,
  teacher_id bigint,
  semester text,
  metric_type text not null,
  anomaly_score numeric not null default 0,
  severity text not null,
  confidence numeric,
  baseline_value numeric,
  current_value numeric,
  absolute_change numeric,
  percentage_change numeric,
  z_score numeric,
  robust_z_score numeric,
  cohort_size int not null default 0,
  affected_student_count int not null default 0,
  affected_percentage numeric,
  window_start timestamptz,
  window_end timestamptz,
  baseline_start timestamptz,
  baseline_end timestamptz,
  first_detected_at timestamptz not null default now(),
  last_observed_at timestamptz not null default now(),
  status text not null default 'NEW',
  explanation text,
  possible_causes jsonb not null default '[]'::jsonb,
  data_quality jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (event_key)
);

create table if not exists public.institutional_anomaly_metrics (
  id bigserial primary key,
  anomaly_id bigint not null references public.institutional_anomalies(id) on delete cascade,
  metric_name text not null,
  baseline numeric,
  current_value numeric,
  deviation numeric,
  z_score numeric,
  robust_z numeric,
  change_percentage numeric,
  confidence numeric
);

create table if not exists public.institutional_anomaly_snapshots (
  id bigserial primary key,
  cohort_key text not null,
  metric_name text not null,
  period_start timestamptz not null,
  period_end timestamptz not null,
  period_kind text not null default 'WEEK',
  value numeric,
  record_count int,
  expected_count int,
  cohort_size int,
  created_at timestamptz not null default now(),
  unique (cohort_key, metric_name, period_start, period_kind)
);

create table if not exists public.institutional_anomaly_notes (
  id bigserial primary key,
  anomaly_id bigint not null references public.institutional_anomalies(id) on delete cascade,
  actor text,
  note text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.institutional_anomaly_settings (
  id int primary key default 1,
  settings jsonb not null default '{}'::jsonb,
  last_analysis_at timestamptz,
  last_analysis jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists idx_inst_anom_institution on public.institutional_anomalies(institution_id);
create index if not exists idx_inst_anom_section on public.institutional_anomalies(section);
create index if not exists idx_inst_anom_semester on public.institutional_anomalies(semester);
create index if not exists idx_inst_anom_subject on public.institutional_anomalies(subject_id);
create index if not exists idx_inst_anom_metric on public.institutional_anomalies(metric_type);
create index if not exists idx_inst_anom_detected on public.institutional_anomalies(first_detected_at);
create index if not exists idx_inst_anom_status on public.institutional_anomalies(status);
create index if not exists idx_inst_anom_severity on public.institutional_anomalies(severity);
create index if not exists idx_inst_anom_identity on public.institutional_anomalies(identity_key);
create index if not exists idx_inst_anom_parent on public.institutional_anomalies(parent_id);
create index if not exists idx_inst_snap_cohort on public.institutional_anomaly_snapshots(cohort_key, metric_name, period_start);
create index if not exists idx_inst_notes_anomaly on public.institutional_anomaly_notes(anomaly_id);

alter table public.institutional_anomalies enable row level security;
alter table public.institutional_anomaly_metrics enable row level security;
alter table public.institutional_anomaly_snapshots enable row level security;
alter table public.institutional_anomaly_notes enable row level security;
alter table public.institutional_anomaly_settings enable row level security;

drop policy if exists "anon_all_institutional_anomalies" on public.institutional_anomalies;
drop policy if exists "anon_all_institutional_anomaly_metrics" on public.institutional_anomaly_metrics;
drop policy if exists "anon_all_institutional_anomaly_snapshots" on public.institutional_anomaly_snapshots;
drop policy if exists "anon_all_institutional_anomaly_notes" on public.institutional_anomaly_notes;
drop policy if exists "anon_all_institutional_anomaly_settings" on public.institutional_anomaly_settings;

create policy "anon_all_institutional_anomalies" on public.institutional_anomalies for all to anon, authenticated using (true) with check (true);
create policy "anon_all_institutional_anomaly_metrics" on public.institutional_anomaly_metrics for all to anon, authenticated using (true) with check (true);
create policy "anon_all_institutional_anomaly_snapshots" on public.institutional_anomaly_snapshots for all to anon, authenticated using (true) with check (true);
create policy "anon_all_institutional_anomaly_notes" on public.institutional_anomaly_notes for all to anon, authenticated using (true) with check (true);
create policy "anon_all_institutional_anomaly_settings" on public.institutional_anomaly_settings for all to anon, authenticated using (true) with check (true);

notify pgrst, 'reload schema';
