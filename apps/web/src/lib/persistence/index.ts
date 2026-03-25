import { hasSupabaseServerConfig } from "@/lib/supabase/server";
import { LocalDocumentRepository } from "./local-document-repository";
import { SupabaseDocumentRepository } from "./supabase-document-repository";
import type { DocumentRepository } from "./types";

let cachedRepository: DocumentRepository | null = null;

export function getDocumentRepository(): DocumentRepository {
  if (!cachedRepository) {
    cachedRepository = hasSupabaseServerConfig() ? new SupabaseDocumentRepository() : new LocalDocumentRepository();
  }

  return cachedRepository;
}
