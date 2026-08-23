-- Additive CLASSORA Predictive Intelligence tables.
-- Does NOT alter students, attendance, risk, mentorship, rewards, or academic_resources.

create table if not exists public.prediction_settings (
  id int primary key default 1,
  settings jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.prediction_documents (
  id bigserial primary key,
  institution_id text not null default 'default',
  owner_student_id bigint,
  uploaded_by text,
  uploaded_role text,
  visibility text not null default 'PRIVATE',
  title text,
  filename text,
  content_hash text,
  document_type text not null default 'UNKNOWN',
  type_override text,
  subject text,
  subject_override text,
  year int,
  semester text,
  academic_year text,
  department text,
  course text,
  domain text,
  source_reliability text,
  official boolean not null default false,
  source_url text,
  extracted_text text,
  status text not null default 'UPLOADED',
  error_message text,
  injection_flag boolean not null default false,
  classification jsonb,
  analyzed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz
);

create index if not exists prediction_documents_hash_idx on public.prediction_documents (institution_id, content_hash);
create index if not exists prediction_documents_owner_idx on public.prediction_documents (owner_student_id);
create index if not exists prediction_documents_type_idx on public.prediction_documents (document_type, subject);

create table if not exists public.prediction_items (
  id bigserial primary key,
  document_id bigint not null,
  item_type text not null,
  raw_text text,
  normalized_text text,
  topic_key text,
  year int,
  marks int,
  extra jsonb,
  created_at timestamptz not null default now()
);

create index if not exists prediction_items_doc_idx on public.prediction_items (document_id);

create table if not exists public.prediction_results (
  id bigserial primary key,
  institution_id text not null default 'default',
  student_id bigint,
  prediction_type text not null,
  subject text,
  mode text,
  prediction jsonb,
  confidence text,
  data_period text,
  status text,
  generated_at timestamptz not null default now(),
  analysis_version text
);

create table if not exists public.prediction_evidence (
  id bigserial primary key,
  prediction_id bigint,
  source_document_id bigint,
  source_reference text,
  evidence_text text,
  relevance_score float,
  kind text,
  created_at timestamptz not null default now()
);

create table if not exists public.prediction_history (
  id bigserial primary key,
  institution_id text not null default 'default',
  student_id bigint,
  question text,
  prediction_type text,
  subject text,
  mode text,
  payload jsonb,
  confidence text,
  status text,
  generated_at timestamptz not null default now(),
  data_period text,
  analysis_version text
);

create table if not exists public.prediction_outcomes (
  id bigserial primary key,
  prediction_id bigint,
  student_id bigint,
  actual_outcome text,
  observed_at timestamptz,
  notes text,
  created_by text,
  created_at timestamptz not null default now()
);

create table if not exists public.prediction_plans (
  id bigserial primary key,
  institution_id text not null default 'default',
  student_id bigint not null,
  subject text,
  mode text,
  items jsonb,
  user_modified boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz
);
