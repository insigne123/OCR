import type { PublicApiClient, TrialUsageSnapshot } from "./public-api-types.ts";
import { countPublicSubmissions } from "./public-api-store.ts";
import {
  TrialAccessError,
  assertTrialClientActive,
  assertTrialQuotaAvailable,
  buildTrialUsageSnapshotFromCount,
  resolveTrialDocumentLimit,
  resolveTrialProcessingMode,
  validateTrialSubmissionRequest,
} from "./public-trial-rules.ts";

export { TrialAccessError, assertTrialClientActive, assertTrialQuotaAvailable, resolveTrialDocumentLimit, resolveTrialProcessingMode, validateTrialSubmissionRequest };

export async function buildTrialUsageSnapshot(client: PublicApiClient): Promise<TrialUsageSnapshot> {
  const used = await countPublicSubmissions({ apiClientId: client.id });
  return buildTrialUsageSnapshotFromCount(client, used);
}
