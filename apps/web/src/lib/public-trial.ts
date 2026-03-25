import type { PublicApiClient, TrialUsageSnapshot } from "./public-api-types.ts";
import { countPublicSubmissions, listUsageLedgerRecords } from "./public-api-store.ts";
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
  const [submissionCount, ledger] = await Promise.all([
    countPublicSubmissions({ apiClientId: client.id }),
    listUsageLedgerRecords({ apiClientId: client.id, eventType: "trial.front_back", limit: 200 }),
  ]);
  const used = submissionCount + ledger.length;
  return buildTrialUsageSnapshotFromCount(client, used);
}
