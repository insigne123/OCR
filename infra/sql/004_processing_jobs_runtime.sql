alter table if exists public.processing_jobs
  add column if not exists attempt_count integer not null default 0,
  add column if not exists max_attempts integer not null default 3,
  add column if not exists next_retry_at timestamptz,
  add column if not exists idempotency_key text,
  add column if not exists queue_name text not null default 'default',
  add column if not exists current_stage text;

create index if not exists idx_processing_jobs_next_retry_at on public.processing_jobs(next_retry_at);
create index if not exists idx_processing_jobs_queue_name on public.processing_jobs(queue_name);
