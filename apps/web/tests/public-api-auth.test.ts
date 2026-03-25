import test from "node:test";
import assert from "node:assert/strict";

import { authenticatePublicApiRequest, authenticateTrialApiRequest, getPublicApiClients, getPublicApiLimits, getTrialApiClients, normalizeRequestedDocumentFamily, normalizeRequestedProcessingMode } from "../src/lib/public-api-auth.ts";
import { derivePublicSubmissionStatus } from "../src/lib/public-api-types.ts";

function buildRequest(headers: Record<string, string> = {}) {
  return new Request("http://localhost/api/public/v1/submissions", { headers });
}

test("public api auth falls back to local dev client when env is absent", () => {
  delete process.env.OCR_PUBLIC_API_KEYS;
  delete process.env.OCR_PUBLIC_API_KEY;
  delete process.env.OCR_PUBLIC_ALLOW_DEV_AUTH;

  const auth = authenticatePublicApiRequest(buildRequest());
  assert.equal(auth.client?.id, "public-local-dev");
  assert.equal(getPublicApiClients()[0]?.tenantId, "public-default-tenant");
});

test("public api auth disables local dev fallback in production", () => {
  const previousNodeEnv = process.env.NODE_ENV;
  process.env.NODE_ENV = "production";
  delete process.env.OCR_PUBLIC_API_KEYS;
  delete process.env.OCR_PUBLIC_API_KEY;
  delete process.env.OCR_PUBLIC_ALLOW_DEV_AUTH;

  const auth = authenticatePublicApiRequest(buildRequest());
  assert.equal(auth.client, null);

  process.env.NODE_ENV = previousNodeEnv;
});

test("public api auth resolves configured x-api-key clients", () => {
  process.env.OCR_PUBLIC_API_KEYS = JSON.stringify([
    { id: "client-a", name: "Client A", tenantId: "tenant-a", apiKey: "secret-a" },
  ]);

  const auth = authenticatePublicApiRequest(buildRequest({ "x-api-key": "secret-a" }));
  assert.equal(auth.client?.tenantId, "tenant-a");

  delete process.env.OCR_PUBLIC_API_KEYS;
});

test("trial api auth resolves dedicated trial clients", () => {
  process.env.OCR_TRIAL_API_KEYS = JSON.stringify([
    { id: "trial-a", name: "Empresa Trial", tenantId: "tenant-trial", apiKey: "trial-secret", documentLimit: 50, expiresAt: "2099-01-01T00:00:00Z" },
  ]);

  const auth = authenticateTrialApiRequest(buildRequest({ authorization: "Bearer trial-secret" }));
  assert.equal(auth.client?.id, "trial-a");
  assert.equal(auth.client?.accessMode, "trial");
  assert.equal(getTrialApiClients()[0]?.documentLimit, 50);

  delete process.env.OCR_TRIAL_API_KEYS;
});

test("public api limits and request normalizers use safe defaults", () => {
  const limits = getPublicApiLimits();
  assert.ok(limits.maxSingleFileBytes > 0);
  assert.equal(normalizeRequestedProcessingMode("queue"), "queue");
  assert.equal(normalizeRequestedProcessingMode("whatever"), "sync");
  assert.equal(normalizeRequestedDocumentFamily("identity"), "identity");
  assert.equal(normalizeRequestedDocumentFamily("bad-value"), "unclassified");
});

test("derivePublicSubmissionStatus maps document states consistently", () => {
  assert.equal(derivePublicSubmissionStatus(null), "failed");
  assert.equal(
    derivePublicSubmissionStatus({
      latestJob: { status: "queued" },
      status: "processing",
      reviewRequired: false,
      decision: "pending",
    } as never),
    "queued"
  );
  assert.equal(
    derivePublicSubmissionStatus({
      latestJob: { status: "completed" },
      status: "review",
      reviewRequired: true,
      decision: "human_review",
    } as never),
    "review"
  );
});
