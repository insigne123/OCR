import test from "node:test";
import assert from "node:assert/strict";

import type { DocumentRecord } from "@ocr/shared";

import { buildAccuracyAnalytics, buildDecisionAnalytics, buildLatencyAnalytics, buildUsageAnalytics } from "../src/lib/public-api-analytics.ts";

function createDocument(overrides: Partial<DocumentRecord> = {}) {
  return {
    id: overrides.id ?? crypto.randomUUID(),
    tenantId: "tenant-a",
    filename: "demo.pdf",
    mimeType: "application/pdf",
    size: 100,
    storagePath: "uploads/demo.pdf",
    storageProvider: "local",
    sourceHash: null,
    status: "completed",
    decision: "auto_accept",
    documentFamily: "identity",
    country: "CL",
    pageCount: 1,
    globalConfidence: 0.93,
    extractedFields: [
      {
        id: "field-1",
        section: "summary",
        fieldName: "run",
        label: "RUN",
        rawText: "12.345.678-5",
        normalizedValue: "12.345.678-5",
        valueType: "text",
        confidence: 0.99,
        engine: "ocr-api",
        pageNumber: 1,
        bbox: null,
        evidenceSpan: null,
        validationStatus: "valid",
        reviewStatus: "confirmed",
        isInferred: false,
        issueIds: [],
        candidates: [],
        consensus: null,
        adjudication: null,
        confidenceDetails: null,
      },
    ],
    reviewSessions: overrides.reviewSessions ?? [],
    processingMetadata: overrides.processingMetadata,
    ...overrides,
  } as DocumentRecord;
}

test("public api analytics summarizes usage and decisions", () => {
  const usage = buildUsageAnalytics([
    {
      id: "1",
      dedupeKey: "submission-terminal:1",
      apiClientId: "client-a",
      tenantId: "tenant-a",
      submissionId: "submission-1",
      batchId: null,
      documentId: "doc-1",
      eventType: "submission.terminal",
      documentFamily: "identity",
      country: "CL",
      decision: "auto_accept",
      status: "completed",
      units: 1,
      bytes: 1024,
      latencyMs: 1200,
      metadata: {},
      createdAt: "2026-03-20T10:00:00.000Z",
    },
    {
      id: "2",
      dedupeKey: "submission-terminal:2",
      apiClientId: "client-a",
      tenantId: "tenant-a",
      submissionId: "submission-2",
      batchId: null,
      documentId: "doc-2",
      eventType: "submission.terminal",
      documentFamily: "certificate",
      country: "CL",
      decision: "human_review",
      status: "review",
      units: 1,
      bytes: 2048,
      latencyMs: 4800,
      metadata: {},
      createdAt: "2026-03-20T11:00:00.000Z",
    },
  ]);

  const decisions = buildDecisionAnalytics([
    {
      id: "1",
      dedupeKey: "submission-terminal:1",
      apiClientId: "client-a",
      tenantId: "tenant-a",
      submissionId: "submission-1",
      batchId: null,
      documentId: "doc-1",
      eventType: "submission.terminal",
      documentFamily: "identity",
      country: "CL",
      decision: "auto_accept",
      status: "completed",
      units: 1,
      bytes: 1024,
      latencyMs: 1200,
      metadata: {},
      createdAt: "2026-03-20T10:00:00.000Z",
    },
    {
      id: "2",
      dedupeKey: "submission-terminal:2",
      apiClientId: "client-a",
      tenantId: "tenant-a",
      submissionId: "submission-2",
      batchId: null,
      documentId: "doc-2",
      eventType: "submission.terminal",
      documentFamily: "certificate",
      country: "CL",
      decision: "human_review",
      status: "review",
      units: 1,
      bytes: 2048,
      latencyMs: 4800,
      metadata: {},
      createdAt: "2026-03-20T11:00:00.000Z",
    },
  ]);

  const latency = buildLatencyAnalytics([
    {
      id: "1",
      dedupeKey: "submission-terminal:1",
      apiClientId: "client-a",
      tenantId: "tenant-a",
      submissionId: "submission-1",
      batchId: null,
      documentId: "doc-1",
      eventType: "submission.terminal",
      documentFamily: "identity",
      country: "CL",
      decision: "auto_accept",
      status: "completed",
      units: 1,
      bytes: 1024,
      latencyMs: 1200,
      metadata: {},
      createdAt: "2026-03-20T10:00:00.000Z",
    },
    {
      id: "2",
      dedupeKey: "submission-terminal:2",
      apiClientId: "client-a",
      tenantId: "tenant-a",
      submissionId: "submission-2",
      batchId: null,
      documentId: "doc-2",
      eventType: "submission.terminal",
      documentFamily: "certificate",
      country: "CL",
      decision: "human_review",
      status: "review",
      units: 1,
      bytes: 2048,
      latencyMs: 4800,
      metadata: {},
      createdAt: "2026-03-20T11:00:00.000Z",
    },
  ]);

  assert.equal(usage.totals.terminalDocuments, 2);
  assert.equal(usage.byFamily[0]?.documents, 1);
  assert.equal(decisions.distribution.auto_accept, 1);
  assert.equal(decisions.distribution.human_review, 1);
  assert.equal(latency.p50, 1200);
  assert.equal(latency.p90, 1200);
  assert.equal(latency.p99, 1200);
});

test("public api analytics estimates accuracy from review edits and feedback", () => {
  const correctedDocument = createDocument({
    id: "doc-1",
    reviewSessions: [
      {
        id: "review-1",
        reviewerName: "Analyst",
        status: "completed",
        notes: null,
        openedAt: "2026-03-20T10:00:00.000Z",
        updatedAt: "2026-03-20T10:05:00.000Z",
        edits: [
          {
            id: "edit-1",
            fieldId: "field-1",
            fieldName: "run",
            previousValue: "12.345.678-0",
            newValue: "12.345.678-5",
            reason: "Client correction",
            createdAt: "2026-03-20T10:03:00.000Z",
            reviewerName: "Analyst",
          },
        ],
      },
    ],
  });

  const accuracy = buildAccuracyAnalytics({
    submissions: [
      {
        id: "submission-1",
        documentId: "doc-1",
        batchId: null,
        apiClientId: "client-a",
        tenantId: "tenant-a",
        externalId: null,
        callbackUrl: null,
        metadata: {},
        filename: "demo.pdf",
        mimeType: "application/pdf",
        size: 1024,
        documentFamily: "identity",
        country: "CL",
        processingMode: "queue",
        source: "upload",
        createdAt: "2026-03-20T10:00:00.000Z",
        updatedAt: "2026-03-20T10:10:00.000Z",
        lastWebhookDelivery: null,
      },
    ],
    documents: [correctedDocument],
    feedback: [
      {
        id: "feedback-1",
        submissionId: "submission-1",
        documentId: "doc-1",
        apiClientId: "client-a",
        tenantId: "tenant-a",
        reviewerName: "Client reviewer",
        notes: null,
        decision: "accept_with_warning",
        corrections: [
          {
            fieldName: "run",
            previousValue: "12.345.678-0",
            newValue: "12.345.678-5",
            reason: "Mismatch",
          },
        ],
        createdAt: "2026-03-20T10:06:00.000Z",
      },
    ],
  });

  assert.equal(accuracy.families[0]?.family, "identity");
  assert.equal(accuracy.families[0]?.correctedDocuments, 1);
  assert.ok((accuracy.families[0]?.estimatedAccuracy ?? 0) < 1);
});
