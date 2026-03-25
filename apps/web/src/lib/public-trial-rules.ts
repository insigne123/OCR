import type { PublicApiClient, TrialUsageSnapshot } from "./public-api-types.ts";

const DEFAULT_TRIAL_DOCUMENT_LIMIT = 50;

export class TrialAccessError extends Error {
  readonly status: number;

  constructor(message: string, status = 400) {
    super(message);
    this.name = "TrialAccessError";
    this.status = status;
  }
}

export function resolveTrialDocumentLimit(client: PublicApiClient) {
  return Math.max(1, client.documentLimit ?? DEFAULT_TRIAL_DOCUMENT_LIMIT);
}

export function resolveTrialProcessingMode(client: PublicApiClient) {
  return client.forceProcessingMode ?? "sync";
}

export function assertTrialClientActive(client: PublicApiClient, now = new Date()) {
  if (client.accessMode !== "trial") {
    throw new TrialAccessError("This token is not enabled for trial access.", 403);
  }
  if (client.expiresAt && new Date(client.expiresAt).getTime() < now.getTime()) {
    throw new TrialAccessError("This trial token has expired.", 403);
  }
}

export function buildTrialUsageSnapshotFromCount(client: PublicApiClient, used: number): TrialUsageSnapshot {
  const limit = resolveTrialDocumentLimit(client);
  return {
    clientId: client.id,
    clientName: client.name,
    companyName: client.name,
    limit,
    used,
    remaining: Math.max(0, limit - used),
    expiresAt: client.expiresAt ?? null,
    processingMode: resolveTrialProcessingMode(client),
  };
}

export function assertTrialQuotaAvailable(usage: TrialUsageSnapshot, requestedDocuments = 1) {
  if (requestedDocuments <= 0) {
    throw new TrialAccessError("Trial requests must include at least one document.", 400);
  }
  if (usage.used + requestedDocuments > usage.limit) {
    throw new TrialAccessError(`Trial limit reached. Used ${usage.used} of ${usage.limit} documents.`, 403);
  }
}

export function validateTrialSubmissionRequest(formData: FormData, client: PublicApiClient) {
  const requestedProcessingMode = String(formData.get("processing_mode") ?? formData.get("processingMode") ?? "sync").toLowerCase();
  if (requestedProcessingMode === "queue") {
    throw new TrialAccessError("The trial endpoint only supports sync processing.", 400);
  }
  if (!client.allowCallbacks) {
    const callbackUrl = formData.get("callback_url") ?? formData.get("callbackUrl");
    if (typeof callbackUrl === "string" && callbackUrl.trim()) {
      throw new TrialAccessError("Callback URLs are disabled for trial tokens.", 400);
    }
  }
}
