import { ensurePublicApiClient } from "@/lib/public-api-auth";
import { buildPublicSubmissionEnvelope, getPublicSubmissionOrThrow } from "@/lib/public-api-status";

type RouteContext = {
  params: Promise<{ submissionId: string }>;
};

export async function GET(request: Request, { params }: RouteContext) {
  const client = ensurePublicApiClient(request);
  if (client instanceof Response) return client;

  const { submissionId } = await params;
  const submission = await getPublicSubmissionOrThrow(submissionId);
  if (!submission || submission.apiClientId !== client.id) {
    return Response.json({ error: "Submission not found." }, { status: 404 });
  }

  return Response.json(await buildPublicSubmissionEnvelope(submission));
}
