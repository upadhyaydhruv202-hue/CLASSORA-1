-- Additive CLASSORA Communities. Does not alter students, attendance, risk, or rewards.

create table if not exists public.community_settings (
  id int primary key default 1,
  settings jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.community_categories (
  id bigserial primary key,
  institution_id text not null default 'default',
  code text not null,
  name text not null,
  active boolean not null default true,
  sort_order int not null default 0,
  updated_at timestamptz,
  unique (institution_id, code)
);

create table if not exists public.communities (
  id bigserial primary key,
  institution_id text not null default 'default',
  name text not null,
  slug text not null,
  category_id bigint,
  category_code text,
  description text,
  purpose text,
  rules text,
  tags jsonb not null default '[]'::jsonb,
  status text not null default 'ACTIVE',
  created_by bigint,
  approved_by text,
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  unique (institution_id, slug)
);

create index if not exists communities_status_idx on public.communities (institution_id, status);
create index if not exists communities_category_idx on public.communities (category_code);
create index if not exists communities_name_idx on public.communities (name);

create table if not exists public.community_members (
  id bigserial primary key,
  community_id bigint not null,
  student_id bigint not null,
  role text not null default 'MEMBER',
  status text not null default 'ACTIVE',
  joined_at timestamptz,
  left_at timestamptz,
  unique (community_id, student_id)
);

create index if not exists community_members_student_idx on public.community_members (student_id, status);

create table if not exists public.community_requests (
  id bigserial primary key,
  institution_id text not null default 'default',
  requested_name text not null,
  category_id bigint,
  category_code text,
  description text,
  purpose text,
  reason text,
  rules text,
  tags jsonb,
  expected_members text,
  banner_url text,
  requested_by bigint not null,
  status text not null default 'PENDING',
  duplicate_flag boolean not null default false,
  duplicate_matches jsonb,
  reviewed_by text,
  reviewed_at timestamptz,
  review_reason text,
  community_id bigint,
  created_at timestamptz not null default now(),
  updated_at timestamptz
);

create index if not exists community_requests_status_idx on public.community_requests (status);

create table if not exists public.community_privacy (
  id bigserial primary key,
  student_id bigint not null unique,
  show_name boolean not null default false,
  show_photo boolean not null default false,
  show_department boolean not null default false,
  show_semester boolean not null default false,
  show_skills boolean not null default false,
  show_bio boolean not null default false,
  show_portfolio boolean not null default false,
  display_name text,
  photo_url text,
  course text,
  semester text,
  skills text,
  bio text,
  portfolio text,
  notify_pref text not null default 'ALL',
  interests jsonb not null default '[]'::jsonb,
  updated_at timestamptz
);

create table if not exists public.community_posts (
  id bigserial primary key,
  community_id bigint not null,
  author_student_id bigint not null,
  kind text not null default 'POST',
  content text,
  link text,
  options jsonb,
  status text not null default 'ACTIVE',
  created_at timestamptz not null default now(),
  updated_at timestamptz
);

create index if not exists community_posts_feed_idx on public.community_posts (community_id, created_at desc);

create table if not exists public.community_comments (
  id bigserial primary key,
  community_id bigint not null,
  post_id bigint not null,
  author_student_id bigint not null,
  content text,
  status text not null default 'ACTIVE',
  created_at timestamptz not null default now()
);

create index if not exists community_comments_post_idx on public.community_comments (post_id, created_at);

create table if not exists public.community_reactions (
  id bigserial primary key,
  community_id bigint,
  post_id bigint not null,
  student_id bigint not null,
  kind text not null,
  extra jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.community_events (
  id bigserial primary key,
  community_id bigint not null,
  title text not null,
  description text,
  start_at text,
  end_at text,
  location text,
  capacity int,
  registration_deadline text,
  created_by bigint,
  status text not null default 'ACTIVE',
  created_at timestamptz not null default now()
);

create index if not exists community_events_start_idx on public.community_events (community_id, start_at);

create table if not exists public.community_event_regs (
  id bigserial primary key,
  event_id bigint not null,
  community_id bigint,
  student_id bigint not null,
  status text not null default 'ACTIVE',
  created_at timestamptz not null default now()
);

create table if not exists public.community_resources (
  id bigserial primary key,
  community_id bigint not null,
  title text not null,
  url text,
  note text,
  category text,
  host text,
  content_hash text,
  created_by bigint,
  status text not null default 'ACTIVE',
  created_at timestamptz not null default now()
);

create table if not exists public.community_reports (
  id bigserial primary key,
  community_id bigint,
  reporter_student_id bigint,
  target_type text,
  post_id bigint,
  comment_id bigint,
  resource_id bigint,
  reported_student_id bigint,
  reason text,
  description text,
  status text not null default 'OPEN',
  resolution text,
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists community_reports_status_idx on public.community_reports (status);

create table if not exists public.community_moderation (
  id bigserial primary key,
  action text not null,
  actor text,
  community_id bigint,
  target_type text,
  target_id text,
  reason text,
  created_at timestamptz not null default now()
);

create table if not exists public.community_blocks (
  id bigserial primary key,
  student_id bigint not null,
  blocked_student_id bigint not null,
  created_at timestamptz not null default now()
);
