-- Additive Institutional Dropout Root-Cause Analyzer.
-- Does NOT alter students, teachers, subjects, attendance, risk, mentorship, or anomaly tables.

create table if not exists public.student_academic_outcomes (
  id bigserial primary key,
  student_id bigint not null,
  status text not null,
  period text,
  notes text,
  recorded_by text,
  recorded_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create table if not exists public.institutional_dropout_analyses (
  id bigserial primary key,
  institution_id text not null default 'default',
  identity_key text not null,
  analysis_version text not null,
  period text not null default 'current',
  insufficient boolean not null default false,
  overview jsonb not null default '{}'::jsonb,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (identity_key)
);

create table if not exists public.institutional_dropout_factors (
  id bigserial primary key,
  analysis_id bigint not null references public.institutional_dropout_analyses(id) on delete cascade,
  factor_id text not null,
  payload jsonb not null default '{}'::jsonb
);

create table if not exists public.institutional_dropout_slices (
  id bigserial primary key,
  analysis_id bigint not null references public.institutional_dropout_analyses(id) on delete cascade,
  slice_kind text not null,
  slice_id text,
  payload jsonb not null default '{}'::jsonb
);

create table if not exists public.institutional_dropout_intersections (
  id bigserial primary key,
  analysis_id bigint not null references public.institutional_dropout_analyses(id) on delete cascade,
  combo text,
  payload jsonb not null default '{}'::jsonb
);

create table if not exists public.institutional_dropout_settings (
  id int primary key default 1,
  settings jsonb not null default '{}'::jsonb,
  last_analysis_at timestamptz,
  last_analysis jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists idx_stu_outcome_student on public.student_academic_outcomes(student_id);
create index if not exists idx_stu_outcome_status on public.student_academic_outcomes(status);
create index if not exists idx_stu_outcome_period on public.student_academic_outcomes(period);
create index if not exists idx_stu_outcome_recorded on public.student_academic_outcomes(recorded_at);
create index if not exists idx_drop_analysis_identity on public.institutional_dropout_analyses(identity_key);
create index if not exists idx_drop_analysis_institution on public.institutional_dropout_analyses(institution_id);
create index if not exists idx_drop_analysis_period on public.institutional_dropout_analyses(period);
create index if not exists idx_drop_factors_analysis on public.institutional_dropout_factors(analysis_id);
create index if not exists idx_drop_slices_analysis on public.institutional_dropout_slices(analysis_id, slice_kind);
create index if not exists idx_drop_inter_analysis on public.institutional_dropout_intersections(analysis_id);

alter table public.student_academic_outcomes enable row level security;
alter table public.institutional_dropout_analyses enable row level security;
alter table public.institutional_dropout_factors enable row level security;
alter table public.institutional_dropout_slices enable row level security;
alter table public.institutional_dropout_intersections enable row level security;
alter table public.institutional_dropout_settings enable row level security;

drop policy if exists "anon_all_student_academic_outcomes" on public.student_academic_outcomes;
drop policy if exists "anon_all_institutional_dropout_analyses" on public.institutional_dropout_analyses;
drop policy if exists "anon_all_institutional_dropout_factors" on public.institutional_dropout_factors;
drop policy if exists "anon_all_institutional_dropout_slices" on public.institutional_dropout_slices;
drop policy if exists "anon_all_institutional_dropout_intersections" on public.institutional_dropout_intersections;
drop policy if exists "anon_all_institutional_dropout_settings" on public.institutional_dropout_settings;

create policy "anon_all_student_academic_outcomes" on public.student_academic_outcomes for all to anon, authenticated using (true) with check (true);
create policy "anon_all_institutional_dropout_analyses" on public.institutional_dropout_analyses for all to anon, authenticated using (true) with check (true);
create policy "anon_all_institutional_dropout_factors" on public.institutional_dropout_factors for all to anon, authenticated using (true) with check (true);
create policy "anon_all_institutional_dropout_slices" on public.institutional_dropout_slices for all to anon, authenticated using (true) with check (true);
create policy "anon_all_institutional_dropout_intersections" on public.institutional_dropout_intersections for all to anon, authenticated using (true) with check (true);
create policy "anon_all_institutional_dropout_settings" on public.institutional_dropout_settings for all to anon, authenticated using (true) with check (true);

notify pgrst, 'reload schema';
