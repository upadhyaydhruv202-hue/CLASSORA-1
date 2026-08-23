-- Additive CLASSORA Rewards (achievement → ledger → wallet → voucher → redemption).
-- Does NOT alter students, attendance, risk, mentorship, or dropout tables.

create table if not exists public.reward_settings (
  id int primary key default 1,
  settings jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.reward_categories (
  id bigserial primary key,
  institution_id text not null default 'default',
  code text not null,
  name text not null,
  active boolean not null default true,
  sort_order int not null default 0,
  unique (institution_id, code)
);

create table if not exists public.reward_policies (
  id bigserial primary key,
  institution_id text not null default 'default',
  version int not null default 1,
  category text not null,
  achievement_type text,
  achievement_level text,
  points int not null check (points >= 0),
  approval_required boolean not null default false,
  active boolean not null default true,
  valid_from timestamptz,
  valid_until timestamptz,
  source text,
  created_at timestamptz not null default now(),
  updated_at timestamptz
);

create table if not exists public.reward_achievements (
  id bigserial primary key,
  institution_id text not null default 'default',
  student_id bigint not null,
  category text not null,
  achievement_type text,
  achievement_level text,
  title text not null,
  description text,
  organization text,
  occurred_at timestamptz,
  certificate_id text,
  event_key text,
  evidence jsonb not null default '{}'::jsonb,
  status text not null,
  proposed_points int,
  awarded_points int,
  policy_ids jsonb,
  submitted_by text,
  submitted_role text,
  review_reason text,
  reviewed_at timestamptz,
  transaction_id bigint,
  idempotency_key text,
  created_at timestamptz not null default now(),
  unique (institution_id, idempotency_key)
);

create table if not exists public.reward_transactions (
  id bigserial primary key,
  institution_id text not null default 'default',
  student_id bigint not null,
  transaction_type text not null,
  points int not null,
  source_type text,
  source_id text,
  category text,
  description text,
  status text not null default 'POSTED',
  issued_by text,
  approved_by text,
  expires_at timestamptz,
  reversed_at timestamptz,
  reversal_reason text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.reward_milestones (
  id bigserial primary key,
  institution_id text not null default 'default',
  student_id bigint not null,
  code text not null,
  points_threshold int not null,
  awarded_at timestamptz not null default now(),
  unique (institution_id, student_id, code)
);

create table if not exists public.reward_badges (
  id bigserial primary key,
  institution_id text not null default 'default',
  student_id bigint not null,
  code text not null,
  title text not null,
  family text,
  source_id text,
  awarded_at timestamptz not null default now(),
  unique (institution_id, student_id, code)
);

create table if not exists public.reward_notice_log (
  id bigserial primary key,
  notice_key text not null unique,
  created_at timestamptz not null default now()
);

create table if not exists public.campus_merchants (
  id bigserial primary key,
  institution_id text not null default 'default',
  name text not null,
  category text not null default 'OTHER',
  location text,
  contact text,
  description text,
  active boolean not null default true,
  access_code_hash text,
  created_at timestamptz not null default now(),
  updated_at timestamptz
);

create table if not exists public.reward_offers (
  id bigserial primary key,
  institution_id text not null default 'default',
  merchant_id bigint not null references public.campus_merchants(id) on delete restrict,
  title text not null,
  description text,
  discount_type text not null,
  discount_value int not null default 0,
  points_cost int not null check (points_cost >= 0),
  min_purchase int not null default 0,
  max_discount int not null default 0,
  redemption_limit int,
  per_student_limit int not null default 1,
  claimed_count int not null default 0,
  valid_from timestamptz,
  valid_until timestamptz,
  active boolean not null default true,
  terms text,
  eligibility jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz
);

create table if not exists public.reward_vouchers (
  id bigserial primary key,
  institution_id text not null default 'default',
  offer_id bigint not null references public.reward_offers(id) on delete restrict,
  merchant_id bigint not null references public.campus_merchants(id) on delete restrict,
  student_id bigint not null,
  token_hash text not null unique,
  token_hint text,
  status text not null,
  points_cost int not null,
  discount_type text,
  discount_value int,
  title text,
  claimed_at timestamptz,
  expires_at timestamptz,
  redeemed_at timestamptz,
  redeemed_by text,
  cancelled_at timestamptz,
  cancel_reason text,
  transaction_id bigint,
  idempotency_key text,
  created_at timestamptz not null default now(),
  unique (institution_id, idempotency_key)
);

create table if not exists public.voucher_redemptions (
  id bigserial primary key,
  institution_id text not null default 'default',
  voucher_id bigint not null references public.reward_vouchers(id) on delete restrict,
  student_id bigint not null,
  merchant_id bigint not null,
  redeemed_by text,
  redeemed_at timestamptz not null default now(),
  verification_method text,
  status text not null default 'CONFIRMED'
);

create index if not exists idx_rew_ach_student on public.reward_achievements(student_id);
create index if not exists idx_rew_ach_status on public.reward_achievements(status);
create index if not exists idx_rew_ach_inst on public.reward_achievements(institution_id);
create index if not exists idx_rew_txn_student on public.reward_transactions(student_id);
create index if not exists idx_rew_txn_type on public.reward_transactions(transaction_type);
create index if not exists idx_rew_txn_created on public.reward_transactions(created_at);
create index if not exists idx_rew_voucher_student on public.reward_vouchers(student_id);
create index if not exists idx_rew_voucher_merchant on public.reward_vouchers(merchant_id);
create index if not exists idx_rew_voucher_status on public.reward_vouchers(status);
create index if not exists idx_rew_voucher_hash on public.reward_vouchers(token_hash);
create index if not exists idx_rew_offer_merchant on public.reward_offers(merchant_id);
create index if not exists idx_rew_red_merchant on public.voucher_redemptions(merchant_id);

alter table public.reward_settings enable row level security;
alter table public.reward_categories enable row level security;
alter table public.reward_policies enable row level security;
alter table public.reward_achievements enable row level security;
alter table public.reward_transactions enable row level security;
alter table public.reward_milestones enable row level security;
alter table public.reward_badges enable row level security;
alter table public.reward_notice_log enable row level security;
alter table public.campus_merchants enable row level security;
alter table public.reward_offers enable row level security;
alter table public.reward_vouchers enable row level security;
alter table public.voucher_redemptions enable row level security;

drop policy if exists "anon_all_reward_settings" on public.reward_settings;
drop policy if exists "anon_all_reward_categories" on public.reward_categories;
drop policy if exists "anon_all_reward_policies" on public.reward_policies;
drop policy if exists "anon_all_reward_achievements" on public.reward_achievements;
drop policy if exists "anon_all_reward_transactions" on public.reward_transactions;
drop policy if exists "anon_all_reward_milestones" on public.reward_milestones;
drop policy if exists "anon_all_reward_badges" on public.reward_badges;
drop policy if exists "anon_all_reward_notice_log" on public.reward_notice_log;
drop policy if exists "anon_all_campus_merchants" on public.campus_merchants;
drop policy if exists "anon_all_reward_offers" on public.reward_offers;
drop policy if exists "anon_all_reward_vouchers" on public.reward_vouchers;
drop policy if exists "anon_all_voucher_redemptions" on public.voucher_redemptions;

create policy "anon_all_reward_settings" on public.reward_settings for all to anon, authenticated using (true) with check (true);
create policy "anon_all_reward_categories" on public.reward_categories for all to anon, authenticated using (true) with check (true);
create policy "anon_all_reward_policies" on public.reward_policies for all to anon, authenticated using (true) with check (true);
create policy "anon_all_reward_achievements" on public.reward_achievements for all to anon, authenticated using (true) with check (true);
create policy "anon_all_reward_transactions" on public.reward_transactions for all to anon, authenticated using (true) with check (true);
create policy "anon_all_reward_milestones" on public.reward_milestones for all to anon, authenticated using (true) with check (true);
create policy "anon_all_reward_badges" on public.reward_badges for all to anon, authenticated using (true) with check (true);
create policy "anon_all_reward_notice_log" on public.reward_notice_log for all to anon, authenticated using (true) with check (true);
create policy "anon_all_campus_merchants" on public.campus_merchants for all to anon, authenticated using (true) with check (true);
create policy "anon_all_reward_offers" on public.reward_offers for all to anon, authenticated using (true) with check (true);
create policy "anon_all_reward_vouchers" on public.reward_vouchers for all to anon, authenticated using (true) with check (true);
create policy "anon_all_voucher_redemptions" on public.voucher_redemptions for all to anon, authenticated using (true) with check (true);

notify pgrst, 'reload schema';
