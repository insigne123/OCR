import { ensureTrialApiClient } from "@/lib/public-api-auth";
import { getOcrApiUrl, getOptionalOcrApiKey } from "@/lib/ocr-config";
import { recordUsageLedgerEvent } from "@/lib/public-api-store";
import { resolveOrProvisionPublicApiTenantId } from "@/lib/public-api-tenants";
import { TrialAccessError, assertTrialClientActive, assertTrialQuotaAvailable, buildTrialUsageSnapshot, resolveTrialProcessingMode } from "@/lib/public-trial";

export async function POST(request: Request) {
  const client = ensureTrialApiClient(request);
  if (client instanceof Response) return client;

  try {
    assertTrialClientActive(client);
    const usage = await buildTrialUsageSnapshot(client);
    assertTrialQuotaAvailable(usage, 1);
    const resolvedTenantId = await resolveOrProvisionPublicApiTenantId(client.tenantId);

    const formData = await request.formData();
    const frontFile = formData.get("front_file");
    const backFile = formData.get("back_file");
    if (!(frontFile instanceof File) || !(backFile instanceof File)) {
      return Response.json({ error: "Both front_file and back_file are required." }, { status: 400 });
    }

    const upstream = new FormData();
    upstream.set("front_file", frontFile, frontFile.name);
    upstream.set("back_file", backFile, backFile.name);
    upstream.set("document_family", String(formData.get("document_family") ?? "identity"));
    upstream.set("country", String(formData.get("country") ?? "CL"));
    upstream.set("response_mode", String(formData.get("response_mode") ?? "full"));
    upstream.set("decision_profile", "balanced");

    const apiKey = getOptionalOcrApiKey();
    const response = await fetch(`${getOcrApiUrl()}/v1/process/front-back`, {
      method: "POST",
      body: upstream,
      cache: "no-store",
      headers: apiKey ? { "x-api-key": apiKey } : undefined,
    });
    if (!response.ok) {
      return Response.json({ error: `OCR API returned ${response.status}` }, { status: 502 });
    }

    const payload = await response.json();
    await recordUsageLedgerEvent({
      dedupeKey: `trial-front-back:${client.id}:${Date.now()}:${frontFile.name}:${backFile.name}`,
      apiClientId: client.id,
      tenantId: resolvedTenantId,
      submissionId: null,
      batchId: null,
      documentId: null,
      eventType: "trial.front_back",
      documentFamily: payload.document_family ?? "identity",
      country: payload.country ?? "CL",
      decision: payload.decision ?? null,
      status: payload.decision === "human_review" ? "review" : "completed",
      units: 1,
      bytes: frontFile.size + backFile.size,
      latencyMs: null,
      metadata: {
        accessMode: "trial",
        processingMode: resolveTrialProcessingMode(client),
        frontFilename: frontFile.name,
        backFilename: backFile.name,
      },
    });

    const nextUsage = await buildTrialUsageSnapshot(client);
    return Response.json({ usage: nextUsage, result: payload });
  } catch (error) {
    if (error instanceof TrialAccessError) {
      return Response.json({ error: error.message }, { status: error.status });
    }
    return Response.json({ error: error instanceof Error ? error.message : "Unexpected front/back error." }, { status: 400 });
  }
}
