import { ensureTrialApiClient } from "@/lib/public-api-auth";
import { TrialAccessError, assertTrialClientActive, buildTrialUsageSnapshot } from "@/lib/public-trial";

export async function GET(request: Request) {
  const client = ensureTrialApiClient(request);
  if (client instanceof Response) return client;

  try {
    assertTrialClientActive(client);
    return Response.json({ usage: await buildTrialUsageSnapshot(client) });
  } catch (error) {
    if (error instanceof TrialAccessError) {
      return Response.json({ error: error.message }, { status: error.status });
    }
    return Response.json({ error: error instanceof Error ? error.message : "Unexpected trial usage error." }, { status: 400 });
  }
}
