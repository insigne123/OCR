alter table if exists public.processing_jobs
  add column if not exists lease_owner text,
  add column if not exists lease_expires_at timestamptz;

create index if not exists idx_processing_jobs_lease_expires_at on public.processing_jobs(lease_expires_at);

create table if not exists public.public_api_webhook_logs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references public.tenants(id) on delete cascade,
  submission_id uuid references public.documents(id) on delete set null,
  batch_id text,
  api_client_id text not null,
  source text not null,
  target_url text not null,
  event_type text not null,
  status text not null default 'pending',
  attempt_count integer not null default 0,
  max_attempts integer not null default 3,
  next_retry_at timestamptz,
  last_attempt_at timestamptz,
  dedupe_key text not null,
  deliveries jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_public_api_webhook_logs_api_client on public.public_api_webhook_logs(api_client_id);
create index if not exists idx_public_api_webhook_logs_status on public.public_api_webhook_logs(status);
create unique index if not exists idx_public_api_webhook_logs_dedupe on public.public_api_webhook_logs(dedupe_key);

create table if not exists public.public_api_usage_ledger (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references public.tenants(id) on delete cascade,
  api_client_id text not null,
  submission_id text,
  batch_id text,
  document_id uuid references public.documents(id) on delete set null,
  event_type text not null,
  document_family text,
  country text,
  decision text,
  status text,
  units integer not null default 1,
  bytes bigint not null default 0,
  latency_ms integer,
  metadata jsonb not null default '{}'::jsonb,
  dedupe_key text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_public_api_usage_ledger_api_client on public.public_api_usage_ledger(api_client_id);
create index if not exists idx_public_api_usage_ledger_created_at on public.public_api_usage_ledger(created_at);
create unique index if not exists idx_public_api_usage_ledger_dedupe on public.public_api_usage_ledger(dedupe_key);

create table if not exists public.public_api_feedback (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references public.tenants(id) on delete cascade,
  api_client_id text not null,
  submission_id text not null,
  document_id uuid references public.documents(id) on delete cascade,
  reviewer_name text,
  notes text,
  decision text,
  corrections jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_public_api_feedback_api_client on public.public_api_feedback(api_client_id);
create index if not exists idx_public_api_feedback_submission on public.public_api_feedback(submission_id);
