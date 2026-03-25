import { ensureTrialApiClient } from "@/lib/public-api-auth";
import { listPublicSubmissions } from "@/lib/public-api-store";
import { createPublicSubmissionFromFormData } from "@/lib/public-api-submissions";
import { buildPublicSubmissionStatus } from "@/lib/public-api-status";
import { TrialAccessError, assertTrialClientActive, assertTrialQuotaAvailable, buildTrialUsageSnapshot, resolveTrialProcessingMode, validateTrialSubmissionRequest } from "@/lib/public-trial";

export async function GET(request: Request) {
  const client = ensureTrialApiClient(request);
  if (client instanceof Response) return client;

  try {
    assertTrialClientActive(client);
    const { searchParams } = new URL(request.url);
    const limit = Number.parseInt(searchParams.get("limit") ?? "20", 10);
    const submissions = await listPublicSubmissions({
      apiClientId: client.id,
      limit: Number.isFinite(limit) ? Math.max(1, Math.min(limit, 50)) : 20,
    });
    return Response.json({
      usage: await buildTrialUsageSnapshot(client),
      items: await Promise.all(submissions.map((submission) => buildPublicSubmissionStatus(submission))),
    });
  } catch (error) {
    if (error instanceof TrialAccessError) {
      return Response.json({ error: error.message }, { status: error.status });
    }
    return Response.json({ error: error instanceof Error ? error.message : "Unexpected trial listing error." }, { status: 400 });
  }
}

export async function POST(request: Request) {
  const client = ensureTrialApiClient(request);
  if (client instanceof Response) return client;

  try {
    assertTrialClientActive(client);
    const usageBefore = await buildTrialUsageSnapshot(client);
    assertTrialQuotaAvailable(usageBefore, 1);
    const formData = await request.formData();
    validateTrialSubmissionRequest(formData, client);
    const payload = await createPublicSubmissionFromFormData(formData, client, {
      forceProcessingMode: resolveTrialProcessingMode(client),
      allowCallbacks: Boolean(client.allowCallbacks),
      augmentMetadata: {
        accessMode: "trial",
        trialClientId: client.id,
        trialClientName: client.name,
      },
    });
    return Response.json(
      {
        ...payload,
        usage: {
          ...usageBefore,
          used: usageBefore.used + 1,
          remaining: Math.max(0, usageBefore.remaining - 1),
        },
      },
      { status: 201 }
    );
  } catch (error) {
    if (error instanceof TrialAccessError) {
      return Response.json({ error: error.message }, { status: error.status });
    }
    return Response.json({ error: error instanceof Error ? error.message : "Unexpected trial submission error." }, { status: 400 });
  }
}
