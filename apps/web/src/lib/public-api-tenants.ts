import { getSupabaseServerClient, hasSupabaseServerConfig } from "@/lib/supabase/server";

const DEFAULT_TENANT_SLUG = process.env.SUPABASE_DEFAULT_TENANT_SLUG || "default-workspace";
const DEFAULT_TENANT_NAME = process.env.SUPABASE_DEFAULT_TENANT_NAME || "Default Workspace";
const PUBLIC_DEFAULT_TENANT_PLACEHOLDER = process.env.OCR_PUBLIC_DEFAULT_TENANT_ID || "public-default-tenant";

function isUuid(value: string | null | undefined) {
  return typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

function normalizeTenantSlug(value: string | null | undefined) {
  const trimmed = value?.trim();
  if (!trimmed || trimmed === PUBLIC_DEFAULT_TENANT_PLACEHOLDER) {
    return DEFAULT_TENANT_SLUG;
  }
  return trimmed;
}

export async function resolveOrProvisionPublicApiTenantId(tenantIdentifier: string | null | undefined) {
  if (!hasSupabaseServerConfig()) {
    return tenantIdentifier ?? PUBLIC_DEFAULT_TENANT_PLACEHOLDER;
  }

  const supabase = getSupabaseServerClient();
  const trimmed = tenantIdentifier?.trim() ?? "";
  if (isUuid(trimmed)) {
    const existing = await supabase.from("tenants").select("id").eq("id", trimmed).maybeSingle();
    if (existing.error) throw new Error(existing.error.message);
    if (existing.data?.id) return existing.data.id;
  }

  const slug = normalizeTenantSlug(trimmed);
  const existing = await supabase.from("tenants").select("id").eq("slug", slug).maybeSingle();
  if (existing.error) throw new Error(existing.error.message);
  if (existing.data?.id) {
    return existing.data.id;
  }

  const created = await supabase
    .from("tenants")
    .insert({
      name: slug === DEFAULT_TENANT_SLUG ? DEFAULT_TENANT_NAME : slug,
      slug,
    })
    .select("id")
    .single();
  if (created.error) throw new Error(created.error.message);
  if (!created.data?.id) {
    throw new Error("Could not provision tenant for public API.");
  }
  return created.data.id;
}
