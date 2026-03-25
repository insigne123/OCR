import { ensurePublicApiClient } from "@/lib/public-api-auth";
import { getPublicBatchById, listPublicBatchSubmissions } from "@/lib/public-api-store";
import { buildPublicSubmissionStatus } from "@/lib/public-api-status";

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

  const submissions = await listPublicBatchSubmissions(batch.id);
  return Response.json({ items: await Promise.all(submissions.map((submission) => buildPublicSubmissionStatus(submission))) });
}
