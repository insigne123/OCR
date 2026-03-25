import { ensurePublicApiClient } from "@/lib/public-api-auth";
import { listPublicBatches } from "@/lib/public-api-store";
import { buildPublicBatchStatus } from "@/lib/public-api-status";

export async function GET(request: Request) {
  const client = ensurePublicApiClient(request);
  if (client instanceof Response) return client;

  const { searchParams } = new URL(request.url);
  const limit = Number.parseInt(searchParams.get("limit") ?? "25", 10);
  const batches = await listPublicBatches({
    apiClientId: client.id,
    limit: Number.isFinite(limit) ? Math.max(1, Math.min(limit, 100)) : 25,
  });
  return Response.json({ items: await Promise.all(batches.map((batch) => buildPublicBatchStatus(batch))) });
}
