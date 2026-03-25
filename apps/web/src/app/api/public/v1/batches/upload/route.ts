import { ensurePublicApiClient, normalizeRequestedDocumentFamily, normalizeRequestedProcessingMode } from "@/lib/public-api-auth";
import { createPublicBatchFromFiles } from "@/lib/public-api-submissions";

function parseMetadata(value: FormDataEntryValue | null) {
  if (typeof value !== "string") return {};
  try {
    const parsed = JSON.parse(value) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

export async function POST(request: Request) {
  const client = ensurePublicApiClient(request);
  if (client instanceof Response) return client;

  try {
    const formData = await request.formData();
    const files = formData.getAll("files").filter((entry): entry is File => entry instanceof File);
    const payload = await createPublicBatchFromFiles({
      client,
      files,
      documentFamily: normalizeRequestedDocumentFamily(formData.get("document_family") ?? formData.get("documentFamily")),
      country: typeof formData.get("country") === "string" ? String(formData.get("country")).toUpperCase() : "XX",
      externalId: typeof formData.get("external_id") === "string" ? (formData.get("external_id") as string) : null,
      callbackUrl: typeof formData.get("callback_url") === "string" ? (formData.get("callback_url") as string) : null,
      metadata: parseMetadata(formData.get("metadata")),
      processingMode: normalizeRequestedProcessingMode(formData.get("processing_mode") ?? formData.get("processingMode")),
    });
    return Response.json(payload, { status: 201 });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Unexpected batch upload error." }, { status: 400 });
  }
}
