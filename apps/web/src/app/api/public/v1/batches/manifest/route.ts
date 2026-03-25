import { ensurePublicApiClient, normalizeRequestedProcessingMode } from "@/lib/public-api-auth";
import { createPublicBatchFromManifest } from "@/lib/public-api-submissions";

type ManifestPayload = {
  external_id?: string | null;
  callback_url?: string | null;
  metadata?: Record<string, unknown>;
  processing_mode?: "sync" | "queue" | null;
  defaults?: {
    document_family?: "certificate" | "identity" | "passport" | "driver_license" | "invoice" | "mixed" | "unclassified";
    country?: string | null;
  };
  items?: Array<{
    file_url: string;
    filename?: string | null;
    document_family?: "certificate" | "identity" | "passport" | "driver_license" | "invoice" | "mixed" | "unclassified";
    country?: string | null;
    external_id?: string | null;
    metadata?: Record<string, unknown>;
  }>;
};

export async function POST(request: Request) {
  const client = ensurePublicApiClient(request);
  if (client instanceof Response) return client;

  try {
    const payload = (await request.json()) as ManifestPayload;
    const created = await createPublicBatchFromManifest({
      client,
      externalId: payload.external_id ?? null,
      callbackUrl: payload.callback_url ?? null,
      metadata: payload.metadata ?? {},
      processingMode: normalizeRequestedProcessingMode(payload.processing_mode),
      defaults: {
        documentFamily: payload.defaults?.document_family,
        country: payload.defaults?.country ?? null,
      },
      items: (payload.items ?? []).map((item) => ({
        fileUrl: item.file_url,
        filename: item.filename ?? null,
        documentFamily: item.document_family,
        country: item.country ?? null,
        externalId: item.external_id ?? null,
        metadata: item.metadata ?? {},
      })),
    });
    return Response.json(created, { status: 201 });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Unexpected manifest batch error." }, { status: 400 });
  }
}
