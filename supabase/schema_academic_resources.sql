-- Additive Student Academic Resource Hub.
-- Does NOT alter students, teachers, subjects, attendance, mentorship, or complaints.

create table if not exists public.academic_resource_sources (
  id bigserial primary key,
  code text not null unique,
  name text not null,
  website_url text not null,
  description text,
  logo_url text,
  organization text,
  section text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.academic_resource_types (
  id bigserial primary key,
  code text not null unique,
  name text not null,
  display_order int not null default 0,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.academic_resource_subjects (
  id bigserial primary key,
  name text not null,
  code text,
  description text,
  year_id text not null,
  semester_id text not null,
  status text not null default 'ACTIVE',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists academic_resource_subjects_unique
  on public.academic_resource_subjects (lower(name), year_id, semester_id);

create table if not exists public.academic_resources (
  id bigserial primary key,
  title text not null,
  description text,
  year_id text not null,
  semester_id text not null,
  subject_id bigint not null references public.academic_resource_subjects(id) on delete restrict,
  resource_type_id bigint not null references public.academic_resource_types(id) on delete restrict,
  source_id bigint not null references public.academic_resource_sources(id) on delete restrict,
  original_url text not null,
  resource_format text not null default 'WEBPAGE',
  is_active boolean not null default true,
  thumbnail_url text,
  tags text,
  display_order int not null default 0,
  created_by text,
  discovery_status text not null default 'VERIFIED',
  last_verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists academic_resources_no_duplicate
  on public.academic_resources (subject_id, resource_type_id, original_url);

create index if not exists academic_resources_year on public.academic_resources (year_id);
create index if not exists academic_resources_semester on public.academic_resources (semester_id);
create index if not exists academic_resources_subject on public.academic_resources (subject_id);
create index if not exists academic_resources_type on public.academic_resources (resource_type_id);
create index if not exists academic_resources_source on public.academic_resources (source_id);
create index if not exists academic_resources_active on public.academic_resources (is_active);

create table if not exists public.academic_resource_reports (
  id bigserial primary key,
  resource_id bigint not null references public.academic_resources(id) on delete cascade,
  student_id bigint references public.students(student_id) on delete set null,
  reason text not null,
  status text not null default 'PENDING',
  created_at timestamptz not null default now(),
  reviewed_at timestamptz
);

create index if not exists academic_resource_reports_resource on public.academic_resource_reports (resource_id, status);

create unique index if not exists academic_resource_reports_one_pending
  on public.academic_resource_reports (resource_id, student_id)
  where status = 'PENDING';

alter table public.academic_resource_sources enable row level security;
alter table public.academic_resource_types enable row level security;
alter table public.academic_resource_subjects enable row level security;
alter table public.academic_resources enable row level security;
alter table public.academic_resource_reports enable row level security;

drop policy if exists "anon_all_academic_resource_sources" on public.academic_resource_sources;
drop policy if exists "anon_all_academic_resource_types" on public.academic_resource_types;
drop policy if exists "anon_all_academic_resource_subjects" on public.academic_resource_subjects;
drop policy if exists "anon_all_academic_resources" on public.academic_resources;
drop policy if exists "anon_all_academic_resource_reports" on public.academic_resource_reports;

create policy "anon_all_academic_resource_sources" on public.academic_resource_sources for all to anon, authenticated using (true) with check (true);
create policy "anon_all_academic_resource_types" on public.academic_resource_types for all to anon, authenticated using (true) with check (true);
create policy "anon_all_academic_resource_subjects" on public.academic_resource_subjects for all to anon, authenticated using (true) with check (true);
create policy "anon_all_academic_resources" on public.academic_resources for all to anon, authenticated using (true) with check (true);
create policy "anon_all_academic_resource_reports" on public.academic_resource_reports for all to anon, authenticated using (true) with check (true);

notify pgrst, 'reload schema';
