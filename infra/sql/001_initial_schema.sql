create extension if not exists pgcrypto;

create table if not exists public.tenants (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text not null unique,
  created_at timestamptz not null default now()
);

create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references public.tenants(id) on delete cascade,
  source_filename text not null,
  mime_type text not null,
  file_size bigint,
  storage_path text not null,
  storage_provider text not null default 'local',
  sha256 text,
  document_family text not null default 'unclassified',
  country text not null default 'CL',
  variant text,
  risk_level text not null default 'medium',
  status text not null default 'uploaded',
  decision text not null default 'pending',
  issuer text,
  holder_name text,
  page_count integer not null default 1,
  global_confidence numeric(4, 3),
  report_html text,
  human_summary text,
  review_required boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  processed_at timestamptz,
  last_reviewed_at timestamptz
);

create table if not exists public.document_pages (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  page_number integer not null,
  image_path text,
  width integer,
  height integer,
  orientation integer,
  quality_score numeric(4, 3),
  blur_score numeric(4, 3),
  glare_score numeric(4, 3),
  has_embedded_text boolean not null default false,
  created_at timestamptz not null default now(),
  unique(document_id, page_number)
);

create table if not exists public.document_classifications (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  page_number integer,
  document_family text not null,
  country text,
  variant text,
  risk_level text,
  confidence numeric(4, 3),
  engine text,
  created_at timestamptz not null default now()
);

create table if not exists public.processing_jobs (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  job_type text not null,
  status text not null default 'queued',
  engine text,
  payload jsonb not null default '{}'::jsonb,
  result jsonb not null default '{}'::jsonb,
  error_message text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz
);

create table if not exists public.extracted_fields (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  page_number integer not null default 1,
  section text not null,
  field_name text not null,
  label text,
  raw_text text,
  normalized_value text,
  value_type text,
  confidence numeric(4, 3),
  engine text,
  bbox jsonb,
  evidence_span jsonb,
  validation_status text not null default 'unknown',
  review_status text not null default 'pending',
  is_inferred boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists public.validation_issues (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  field_name text not null,
  issue_type text not null,
  severity text not null,
  message text not null,
  suggested_action text,
  created_at timestamptz not null default now()
);

create table if not exists public.generated_reports (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  format text not null,
  storage_path text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.review_sessions (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  reviewer_id uuid,
  reviewer_name text,
  status text not null default 'open',
  notes text,
  created_at timestamptz not null default now(),
  closed_at timestamptz
);

create table if not exists public.review_edits (
  id uuid primary key default gen_random_uuid(),
  review_session_id uuid not null references public.review_sessions(id) on delete cascade,
  document_id uuid not null references public.documents(id) on delete cascade,
  field_id uuid,
  field_name text not null,
  previous_value text,
  new_value text,
  reason text,
  reviewer_name text,
  created_at timestamptz not null default now()
);

create table if not exists public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references public.tenants(id) on delete cascade,
  document_id uuid references public.documents(id) on delete cascade,
  actor_id uuid,
  action text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_documents_tenant_id on public.documents(tenant_id);
create index if not exists idx_documents_status on public.documents(status);
create index if not exists idx_processing_jobs_document_id on public.processing_jobs(document_id);
create index if not exists idx_document_pages_document_id on public.document_pages(document_id);
create index if not exists idx_document_classifications_document_id on public.document_classifications(document_id);
create index if not exists idx_extracted_fields_document_id on public.extracted_fields(document_id);
create index if not exists idx_validation_issues_document_id on public.validation_issues(document_id);
create index if not exists idx_review_sessions_document_id on public.review_sessions(document_id);
