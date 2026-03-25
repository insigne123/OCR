alter table if exists public.documents
  add column if not exists pack_id text,
  add column if not exists pack_version text,
  add column if not exists document_side text,
  add column if not exists cross_side_detected boolean not null default false,
  add column if not exists classification_confidence numeric(4, 3),
  add column if not exists extraction_source text,
  add column if not exists processing_engine text;

create index if not exists idx_documents_pack_id on public.documents(pack_id);
create index if not exists idx_documents_document_side on public.documents(document_side);
