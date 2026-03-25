import test from "node:test";
import assert from "node:assert/strict";

import type { PublicApiClient } from "../src/lib/public-api-types.ts";
import { TrialAccessError, assertTrialClientActive, assertTrialQuotaAvailable, buildTrialUsageSnapshotFromCount, resolveTrialDocumentLimit, resolveTrialProcessingMode, validateTrialSubmissionRequest } from "../src/lib/public-trial-rules.ts";

function buildTrialClient(overrides: Partial<PublicApiClient> = {}): PublicApiClient {
  return {
    id: "trial-client",
    name: "Empresa Demo",
    tenantId: "tenant-demo",
    apiKey: "trial-token",
    accessMode: "trial",
    documentLimit: 50,
    expiresAt: null,
    allowCallbacks: false,
    forceProcessingMode: "sync",
    ...overrides,
  };
}

test("trial helpers expose default limits and sync mode", () => {
  const client = buildTrialClient();
  assert.equal(resolveTrialDocumentLimit(client), 50);
  assert.equal(resolveTrialProcessingMode(client), "sync");
});

test("trial helpers block expired tokens", () => {
  const client = buildTrialClient({ expiresAt: "2020-01-01T00:00:00Z" });
  assert.throws(() => assertTrialClientActive(client), TrialAccessError);
});

test("trial helpers block quota overflow", () => {
  const usage = buildTrialUsageSnapshotFromCount(buildTrialClient(), 50);
  assert.throws(() => assertTrialQuotaAvailable(usage, 1), TrialAccessError);
});

test("trial submission validation blocks queue mode and callbacks", () => {
  const client = buildTrialClient();
  const queueForm = new FormData();
  queueForm.set("processing_mode", "queue");
  assert.throws(() => validateTrialSubmissionRequest(queueForm, client), TrialAccessError);

  const callbackForm = new FormData();
  callbackForm.set("callback_url", "https://client.example.com/webhook");
  assert.throws(() => validateTrialSubmissionRequest(callbackForm, client), TrialAccessError);
});

test("trial submission validation allows clean sync submissions", () => {
  const client = buildTrialClient();
  const form = new FormData();
  form.set("document_family", "certificate");
  form.set("country", "CL");
  assert.doesNotThrow(() => validateTrialSubmissionRequest(form, client));
});
