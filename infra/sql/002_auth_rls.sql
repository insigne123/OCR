create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  display_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.tenant_members (
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  role text not null default 'member' check (role in ('admin', 'member', 'reviewer')),
  created_at timestamptz not null default now(),
  primary key (tenant_id, user_id)
);

create or replace function public.set_timestamp_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_profiles_updated_at on public.profiles;
create trigger trg_profiles_updated_at
before update on public.profiles
for each row execute function public.set_timestamp_updated_at();

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, display_name)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'name', new.email)
  )
  on conflict (id) do update
  set email = excluded.email,
      display_name = excluded.display_name,
      updated_at = now();

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_user();

create or replace function public.is_tenant_member(target_tenant uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.tenant_members tm
    where tm.tenant_id = target_tenant
      and tm.user_id = auth.uid()
  );
$$;

create or replace function public.is_tenant_admin(target_tenant uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.tenant_members tm
    where tm.tenant_id = target_tenant
      and tm.user_id = auth.uid()
      and tm.role = 'admin'
  );
$$;

create index if not exists idx_tenant_members_user_id on public.tenant_members(user_id);

alter table public.profiles enable row level security;
alter table public.tenant_members enable row level security;
alter table public.tenants enable row level security;
alter table public.documents enable row level security;
alter table public.document_pages enable row level security;
alter table public.document_classifications enable row level security;
alter table public.processing_jobs enable row level security;
alter table public.extracted_fields enable row level security;
alter table public.validation_issues enable row level security;
alter table public.generated_reports enable row level security;
alter table public.review_sessions enable row level security;
alter table public.review_edits enable row level security;
alter table public.audit_logs enable row level security;

drop policy if exists profiles_select_self on public.profiles;
create policy profiles_select_self on public.profiles
for select
to authenticated
using (id = auth.uid());

drop policy if exists profiles_update_self on public.profiles;
create policy profiles_update_self on public.profiles
for update
to authenticated
using (id = auth.uid())
with check (id = auth.uid());

drop policy if exists tenant_members_select_self on public.tenant_members;
create policy tenant_members_select_self on public.tenant_members
for select
to authenticated
using (user_id = auth.uid());

drop policy if exists tenants_select_member on public.tenants;
create policy tenants_select_member on public.tenants
for select
to authenticated
using (public.is_tenant_member(id));

drop policy if exists tenants_update_admin on public.tenants;
create policy tenants_update_admin on public.tenants
for update
to authenticated
using (public.is_tenant_admin(id))
with check (public.is_tenant_admin(id));

drop policy if exists documents_select_member on public.documents;
create policy documents_select_member on public.documents
for select
to authenticated
using (public.is_tenant_member(tenant_id));

drop policy if exists documents_insert_admin on public.documents;
create policy documents_insert_admin on public.documents
for insert
to authenticated
with check (public.is_tenant_admin(tenant_id));

drop policy if exists documents_update_admin on public.documents;
create policy documents_update_admin on public.documents
for update
to authenticated
using (public.is_tenant_admin(tenant_id))
with check (public.is_tenant_admin(tenant_id));

drop policy if exists documents_delete_admin on public.documents;
create policy documents_delete_admin on public.documents
for delete
to authenticated
using (public.is_tenant_admin(tenant_id));

drop policy if exists document_pages_select_member on public.document_pages;
create policy document_pages_select_member on public.document_pages
for select
to authenticated
using (
  exists (
    select 1 from public.documents d
    where d.id = document_pages.document_id
      and public.is_tenant_member(d.tenant_id)
  )
);

drop policy if exists document_classifications_select_member on public.document_classifications;
create policy document_classifications_select_member on public.document_classifications
for select
to authenticated
using (
  exists (
    select 1 from public.documents d
    where d.id = document_classifications.document_id
      and public.is_tenant_member(d.tenant_id)
  )
);

drop policy if exists processing_jobs_select_member on public.processing_jobs;
create policy processing_jobs_select_member on public.processing_jobs
for select
to authenticated
using (
  exists (
    select 1 from public.documents d
    where d.id = processing_jobs.document_id
      and public.is_tenant_member(d.tenant_id)
  )
);

drop policy if exists extracted_fields_select_member on public.extracted_fields;
create policy extracted_fields_select_member on public.extracted_fields
for select
to authenticated
using (
  exists (
    select 1 from public.documents d
    where d.id = extracted_fields.document_id
      and public.is_tenant_member(d.tenant_id)
  )
);

drop policy if exists validation_issues_select_member on public.validation_issues;
create policy validation_issues_select_member on public.validation_issues
for select
to authenticated
using (
  exists (
    select 1 from public.documents d
    where d.id = validation_issues.document_id
      and public.is_tenant_member(d.tenant_id)
  )
);

drop policy if exists generated_reports_select_member on public.generated_reports;
create policy generated_reports_select_member on public.generated_reports
for select
to authenticated
using (
  exists (
    select 1 from public.documents d
    where d.id = generated_reports.document_id
      and public.is_tenant_member(d.tenant_id)
  )
);

drop policy if exists review_sessions_select_member on public.review_sessions;
create policy review_sessions_select_member on public.review_sessions
for select
to authenticated
using (
  exists (
    select 1 from public.documents d
    where d.id = review_sessions.document_id
      and public.is_tenant_member(d.tenant_id)
  )
);

drop policy if exists review_edits_select_member on public.review_edits;
create policy review_edits_select_member on public.review_edits
for select
to authenticated
using (
  exists (
    select 1 from public.documents d
    where d.id = review_edits.document_id
      and public.is_tenant_member(d.tenant_id)
  )
);

drop policy if exists audit_logs_select_member on public.audit_logs;
create policy audit_logs_select_member on public.audit_logs
for select
to authenticated
using (tenant_id is not null and public.is_tenant_member(tenant_id));
