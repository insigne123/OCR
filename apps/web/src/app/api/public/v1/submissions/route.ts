import { ensurePublicApiClient } from "@/lib/public-api-auth";
import { listPublicSubmissions } from "@/lib/public-api-store";
import { createPublicSubmissionFromFormData } from "@/lib/public-api-submissions";
import { buildPublicSubmissionStatus } from "@/lib/public-api-status";

export async function GET(request: Request) {
  const client = ensurePublicApiClient(request);
  if (client instanceof Response) return client;

  const { searchParams } = new URL(request.url);
  const limit = Number.parseInt(searchParams.get("limit") ?? "50", 10);
  const batchId = searchParams.get("batch_id");
  const submissions = await listPublicSubmissions({
    apiClientId: client.id,
    batchId: batchId || null,
    limit: Number.isFinite(limit) ? Math.max(1, Math.min(limit, 100)) : 50,
  });
  return Response.json({ items: await Promise.all(submissions.map((submission) => buildPublicSubmissionStatus(submission))) });
}

export async function POST(request: Request) {
  const client = ensurePublicApiClient(request);
  if (client instanceof Response) return client;

  try {
    const formData = await request.formData();
    const payload = await createPublicSubmissionFromFormData(formData, client);
    return Response.json(payload, { status: 201 });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "Unexpected submission error." }, { status: 400 });
  }
}
