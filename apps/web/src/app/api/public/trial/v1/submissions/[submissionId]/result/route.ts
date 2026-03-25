import { ensureTrialApiClient } from "@/lib/public-api-auth";
import { buildPublicResultSummary, buildPublicSubmissionEnvelope, getPublicSubmissionOrThrow } from "@/lib/public-api-status";
import { TrialAccessError, assertTrialClientActive, buildTrialUsageSnapshot } from "@/lib/public-trial";

type RouteContext = {
  params: Promise<{ submissionId: string }>;
};

export async function GET(request: Request, { params }: RouteContext) {
  const client = ensureTrialApiClient(request);
  if (client instanceof Response) return client;

  try {
    assertTrialClientActive(client);
    const { submissionId } = await params;
    const submission = await getPublicSubmissionOrThrow(submissionId);
    if (!submission || submission.apiClientId !== client.id) {
      return Response.json({ error: "Submission not found." }, { status: 404 });
    }
    const envelope = await buildPublicSubmissionEnvelope(submission);
    const view = new URL(request.url).searchParams.get("view");
    return Response.json({ usage: await buildTrialUsageSnapshot(client), ...((view === "full") ? envelope : buildPublicResultSummary(envelope)) });
  } catch (error) {
    if (error instanceof TrialAccessError) {
      return Response.json({ error: error.message }, { status: error.status });
    }
    return Response.json({ error: error instanceof Error ? error.message : "Unexpected trial result error." }, { status: 400 });
  }
}
