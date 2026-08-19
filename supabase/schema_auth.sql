-- Additive auth tables for Features 01 (Authentication & Access).
-- Run in Supabase SQL Editor. Does not alter existing ML/attendance tables.

create table if not exists public.auth_events (
  id bigserial primary key,
  username text,
  role text,
  event text not null,
  status text not null default 'ok',
  created_at timestamptz not null default now()
);

create index if not exists idx_auth_events_created_at on public.auth_events(created_at desc);
create index if not exists idx_auth_events_username on public.auth_events(username);

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

create index if not exists idx_teacher_invites_username on public.teacher_invites(invited_username);

alter table public.auth_events enable row level security;
alter table public.teacher_invites enable row level security;

drop policy if exists "anon_all_auth_events" on public.auth_events;
drop policy if exists "anon_all_teacher_invites" on public.teacher_invites;

create policy "anon_all_auth_events" on public.auth_events
  for all to anon, authenticated using (true) with check (true);
create policy "anon_all_teacher_invites" on public.teacher_invites
  for all to anon, authenticated using (true) with check (true);

notify pgrst, 'reload schema';
