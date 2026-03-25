create table if not exists public.public_api_batches (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  api_client_id text not null,
  external_id text,
  callback_url text,
  metadata jsonb not null default '{}'::jsonb,
  source text not null,
  submission_ids uuid[] not null default '{}'::uuid[],
  last_webhook_delivery jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.public_api_submissions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  document_id uuid not null references public.documents(id) on delete cascade,
  batch_id uuid references public.public_api_batches(id) on delete set null,
  api_client_id text not null,
  external_id text,
  callback_url text,
  metadata jsonb not null default '{}'::jsonb,
  filename text not null,
  mime_type text not null,
  size bigint not null default 0,
  document_family text not null,
  country text not null,
  processing_mode text not null,
  source text not null,
  last_webhook_delivery jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_public_api_batches_api_client_id on public.public_api_batches(api_client_id);
create index if not exists idx_public_api_batches_tenant_id on public.public_api_batches(tenant_id);
create index if not exists idx_public_api_submissions_api_client_id on public.public_api_submissions(api_client_id);
create index if not exists idx_public_api_submissions_batch_id on public.public_api_submissions(batch_id);
create index if not exists idx_public_api_submissions_document_id on public.public_api_submissions(document_id);

alter table if exists public.public_api_webhook_logs
  add column if not exists document_id uuid references public.documents(id) on delete set null,
  add column if not exists updated_at timestamptz not null default now();

alter table if exists public.public_api_feedback
  add column if not exists tenant_id uuid references public.tenants(id) on delete cascade,
  add column if not exists api_client_id text,
  add column if not exists document_id uuid references public.documents(id) on delete cascade;

alter table if exists public.public_api_webhook_logs
  drop constraint if exists public_api_webhook_logs_submission_id_fkey;

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'public_api_webhook_logs'
      and column_name = 'submission_id'
      and data_type <> 'uuid'
  ) then
    alter table public.public_api_webhook_logs
      alter column submission_id type uuid using nullif(submission_id::text, '')::uuid;
  end if;
end $$;

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'public_api_webhook_logs'
      and column_name = 'batch_id'
      and data_type <> 'uuid'
  ) then
    alter table public.public_api_webhook_logs
      alter column batch_id type uuid using nullif(batch_id::text, '')::uuid;
  end if;
end $$;

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'public_api_feedback'
      and column_name = 'submission_id'
      and data_type <> 'uuid'
  ) then
    alter table public.public_api_feedback
      alter column submission_id type uuid using nullif(submission_id::text, '')::uuid;
  end if;
end $$;

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'public_api_feedback'
      and column_name = 'batch_id'
  ) then
    begin
      alter table public.public_api_feedback
        alter column batch_id type uuid using nullif(batch_id::text, '')::uuid;
    exception when undefined_column then
      null;
    end;
  end if;
end $$;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'public_api_webhook_logs_submission_id_fkey'
  ) then
    alter table public.public_api_webhook_logs
      add constraint public_api_webhook_logs_submission_id_fkey
      foreign key (submission_id) references public.public_api_submissions(id) on delete set null;
  end if;
end $$;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'public_api_webhook_logs_batch_id_fkey'
  ) then
    alter table public.public_api_webhook_logs
      add constraint public_api_webhook_logs_batch_id_fkey
      foreign key (batch_id) references public.public_api_batches(id) on delete set null;
  end if;
end $$;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'public_api_feedback_submission_id_fkey'
  ) then
    alter table public.public_api_feedback
      add constraint public_api_feedback_submission_id_fkey
      foreign key (submission_id) references public.public_api_submissions(id) on delete cascade;
  end if;
end $$;

drop trigger if exists trg_public_api_batches_updated_at on public.public_api_batches;
create trigger trg_public_api_batches_updated_at
before update on public.public_api_batches
for each row execute function public.set_timestamp_updated_at();

drop trigger if exists trg_public_api_submissions_updated_at on public.public_api_submissions;
create trigger trg_public_api_submissions_updated_at
before update on public.public_api_submissions
for each row execute function public.set_timestamp_updated_at();

drop trigger if exists trg_public_api_webhook_logs_updated_at on public.public_api_webhook_logs;
create trigger trg_public_api_webhook_logs_updated_at
before update on public.public_api_webhook_logs
for each row execute function public.set_timestamp_updated_at();

alter table public.public_api_batches enable row level security;
alter table public.public_api_submissions enable row level security;
alter table public.public_api_webhook_logs enable row level security;
alter table public.public_api_usage_ledger enable row level security;
alter table public.public_api_feedback enable row level security;

drop policy if exists public_api_batches_select_member on public.public_api_batches;
create policy public_api_batches_select_member on public.public_api_batches
for select to authenticated
using (public.is_tenant_member(tenant_id));

drop policy if exists public_api_submissions_select_member on public.public_api_submissions;
create policy public_api_submissions_select_member on public.public_api_submissions
for select to authenticated
using (public.is_tenant_member(tenant_id));

drop policy if exists public_api_webhook_logs_select_member on public.public_api_webhook_logs;
create policy public_api_webhook_logs_select_member on public.public_api_webhook_logs
for select to authenticated
using (tenant_id is not null and public.is_tenant_member(tenant_id));

drop policy if exists public_api_usage_ledger_select_member on public.public_api_usage_ledger;
create policy public_api_usage_ledger_select_member on public.public_api_usage_ledger
for select to authenticated
using (tenant_id is not null and public.is_tenant_member(tenant_id));

drop policy if exists public_api_feedback_select_member on public.public_api_feedback;
create policy public_api_feedback_select_member on public.public_api_feedback
for select to authenticated
using (tenant_id is not null and public.is_tenant_member(tenant_id));
