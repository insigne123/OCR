import { ensurePublicApiClient } from "@/lib/public-api-auth";
import { getPublicBatchById } from "@/lib/public-api-store";
import { buildPublicBatchStatus } from "@/lib/public-api-status";

type RouteContext = {
  params: Promise<{ batchId: string }>;
};

export async function GET(request: Request, { params }: RouteContext) {
  const client = ensurePublicApiClient(request);
  if (client instanceof Response) return client;

  const { batchId } = await params;
  const batch = await getPublicBatchById(batchId);
  if (!batch || batch.apiClientId !== client.id) {
    return Response.json({ error: "Batch not found." }, { status: 404 });
  }

  return Response.json({ batch: await buildPublicBatchStatus(batch) });
}
