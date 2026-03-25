import type { DocumentRecord } from "@ocr/shared";

import { getDocumentByIdInternal } from "@/lib/document-store";
import {
  getPublicBatchById,
  getPublicSubmissionByDocumentId,
  getPublicSubmissionById,
  getWebhookLogById,
  listPublicBatchSubmissions,
  recordUsageLedgerEvent,
} from "@/lib/public-api-store";
import { attemptWebhookDelivery, drainPublicWebhookQueue, enqueuePublicWebhook, requeuePublicWebhookLog } from "@/lib/public-api-webhooks";
import type {
  PublicBatchRecord,
  PublicBatchStatus,
  PublicBatchStatusSnapshot,
  PublicSubmissionRecord,
  PublicSubmissionResult,
  PublicSubmissionStatus,
  PublicSubmissionStatusSnapshot,
  PublicWebhookDelivery,
} from "@/lib/public-api-types";
import { derivePublicSubmissionStatus } from "@/lib/public-api-types";

function terminalSubmissionStatus(status: PublicSubmissionStatus) {
  return ["completed", "review", "rejected", "failed"].includes(status);
}

function terminalBatchStatus(status: PublicBatchStatus) {
  return ["completed", "partial", "failed"].includes(status);
}

function eventTypeForSubmissionStatus(status: PublicSubmissionStatus) {
  if (status === "review") return "submission.review_required";
  if (status === "rejected") return "submission.rejected";
  if (status === "failed") return "submission.failed";
  return "submission.completed";
}

function eventTypeForBatchStatus(status: PublicBatchStatus) {
  if (status === "failed") return "batch.failed";
  if (status === "partial") return "batch.partial";
  return "batch.completed";
}

function resultUrlForSubmission(submissionId: string) {
  return `/api/public/v1/submissions/${submissionId}/result`;
}

function resolveLatencyMs(document: DocumentRecord | null) {
  if (!document) return null;
  if (document.latestJob?.startedAt && document.latestJob?.finishedAt) {
    return Math.max(0, new Date(document.latestJob.finishedAt).getTime() - new Date(document.latestJob.startedAt).getTime());
  }
  if (document.processingMetadata.processingTrace.length > 0) {
    return Math.round(document.processingMetadata.processingTrace.reduce((acc, entry) => acc + entry.durationMs, 0));
  }
  return null;
}

async function buildWebhookPayloadForLog(log: {
  source: "submission" | "batch" | "document";
  eventType: string;
  submissionId: string | null;
  batchId: string | null;
}) {
  if (log.source === "submission" && log.submissionId) {
    const submission = await getPublicSubmissionById(log.submissionId);
    if (!submission) return { event: log.eventType };
    return {
      event: log.eventType,
      submission: await buildPublicSubmissionStatus(submission),
      result: await buildPublicSubmissionEnvelope(submission),
    };
  }

  if (log.batchId) {
    const batch = await getPublicBatchById(log.batchId);
    if (!batch) return { event: log.eventType };
    const items = await Promise.all((await listPublicBatchSubmissions(batch.id)).map((submission) => buildPublicSubmissionStatus(submission)));
    return {
      event: log.eventType,
      batch: await buildPublicBatchStatus(batch),
      items,
    };
  }

  return { event: log.eventType };
}

async function ensureSubmissionDocumentReady(documentId: string) {
  const initialDocument = await getDocumentByIdInternal(documentId);
  if (!initialDocument) {
    return null;
  }
  if (initialDocument.latestJob?.status !== "completed") {
    return initialDocument;
  }

  const processing = await import("@/lib/document-processing");
  if (processing.hasMaterializedProcessingResult(initialDocument)) {
    return initialDocument;
  }

  return processing.finalizeProcessedDocument(documentId, initialDocument);
}

async function recordSubmissionUsage(submission: PublicSubmissionRecord, document: DocumentRecord, status: PublicSubmissionStatus) {
  await recordUsageLedgerEvent({
    dedupeKey: `submission-terminal:${submission.id}:${status}:${document.processedAt ?? document.updatedAt}`,
    apiClientId: submission.apiClientId,
    tenantId: submission.tenantId,
    submissionId: submission.id,
    batchId: submission.batchId,
    documentId: submission.documentId,
    eventType: "submission.terminal",
    documentFamily: document.documentFamily,
    country: document.country,
    decision: document.decision,
    status,
    units: 1,
    bytes: submission.size,
    latencyMs: resolveLatencyMs(document),
    metadata: {
      callbackConfigured: Boolean(submission.callbackUrl),
      processingMode: submission.processingMode,
      packId: document.processingMetadata.packId,
      classificationConfidence: document.processingMetadata.classificationConfidence,
    },
  });
}

async function recordBatchUsage(batch: PublicBatchRecord, snapshot: PublicBatchStatusSnapshot) {
  await recordUsageLedgerEvent({
    dedupeKey: `batch-terminal:${batch.id}:${snapshot.status}:${snapshot.updatedAt}`,
    apiClientId: batch.apiClientId,
    tenantId: batch.tenantId,
    submissionId: null,
    batchId: batch.id,
    documentId: null,
    eventType: "batch.terminal",
    documentFamily: null,
    country: null,
    decision: null,
    status: snapshot.status,
    units: snapshot.itemCount,
    bytes: 0,
    latencyMs: null,
    metadata: {
      completed: snapshot.completed,
      review: snapshot.review,
      rejected: snapshot.rejected,
      failed: snapshot.failed,
    },
  });
}

export async function buildPublicSubmissionStatus(submission: PublicSubmissionRecord): Promise<PublicSubmissionStatusSnapshot> {
  const document = await ensureSubmissionDocumentReady(submission.documentId);
  const status = derivePublicSubmissionStatus(document);
  return {
    submissionId: submission.id,
    externalId: submission.externalId,
    documentId: submission.documentId,
    batchId: submission.batchId,
    status,
    filename: submission.filename,
    mimeType: submission.mimeType,
    size: submission.size,
    documentFamily: submission.documentFamily,
    country: submission.country,
    tenantId: submission.tenantId,
    callbackUrl: submission.callbackUrl,
    processingMode: submission.processingMode,
    createdAt: submission.createdAt,
    updatedAt: submission.updatedAt,
    lastWebhookDelivery: submission.lastWebhookDelivery,
    latestDecision: document?.decision ?? "pending",
    globalConfidence: document?.globalConfidence ?? null,
    reviewRequired: document?.reviewRequired ?? false,
    processedAt: document?.processedAt ?? null,
  };
}

export async function buildPublicSubmissionResult(submission: PublicSubmissionRecord): Promise<PublicSubmissionResult | null> {
  const document = await ensureSubmissionDocumentReady(submission.documentId);
  if (!document) return null;
  const status = derivePublicSubmissionStatus(document);
  return {
    submissionId: submission.id,
    externalId: submission.externalId,
    status,
    filename: submission.filename,
    documentId: submission.documentId,
    documentFamily: document.documentFamily,
    country: document.country,
    decision: document.decision,
    globalConfidence: document.globalConfidence,
    reviewRequired: document.reviewRequired,
    processedAt: document.processedAt,
    resultUrl: resultUrlForSubmission(submission.id),
    callbackUrl: submission.callbackUrl,
  };
}

export async function buildPublicSubmissionEnvelope(submission: PublicSubmissionRecord) {
  const document = await ensureSubmissionDocumentReady(submission.documentId);
  const status = derivePublicSubmissionStatus(document);
  return {
    submission: await buildPublicSubmissionStatus(submission),
    result: document
      ? {
          documentId: document.id,
          status,
          decision: document.decision,
          reviewRequired: document.reviewRequired,
          processedAt: document.processedAt,
          globalConfidence: document.globalConfidence,
          documentFamily: document.documentFamily,
          country: document.country,
          variant: document.variant,
          issuer: document.issuer,
          holderName: document.holderName,
          issues: document.issues,
          reportSections: document.reportSections,
          extractedFields: document.extractedFields,
          processingMetadata: document.processingMetadata,
          assumptions: document.assumptions,
        }
      : null,
  };
}

export function buildPublicResultSummary(envelope: Awaited<ReturnType<typeof buildPublicSubmissionEnvelope>>) {
  const result = envelope.result;
  if (!result) {
    return envelope;
  }

  const keyFieldNames = new Set([
    "nombre-completo",
    "nombres",
    "apellidos",
    "run",
    "numero-de-documento",
    "numero",
    "fecha-de-nacimiento",
    "fecha-de-emision",
    "fecha-de-vencimiento",
    "sexo",
    "nacionalidad",
    "lugar-de-nacimiento",
  ]);

  return {
    submission: envelope.submission,
    result: {
      documentId: result.documentId,
      status: result.status,
      decision: result.decision,
      reviewRequired: result.reviewRequired,
      processedAt: result.processedAt,
      globalConfidence: result.globalConfidence,
      documentFamily: result.documentFamily,
      country: result.country,
      variant: result.variant,
      issuer: result.issuer,
      holderName: result.holderName,
      keyFields: result.extractedFields
        .filter((field) => keyFieldNames.has(field.fieldName))
        .slice(0, 12)
        .map((field) => ({
          fieldName: field.fieldName,
          label: field.label,
          value: field.normalizedValue,
          confidence: field.confidence,
          pageNumber: field.pageNumber,
        })),
      issues: result.issues.slice(0, 6),
      processingMetadata: {
        documentSide: result.processingMetadata.documentSide,
        classificationConfidence: result.processingMetadata.classificationConfidence,
        extractionSource: result.processingMetadata.extractionSource,
        processingEngine: result.processingMetadata.processingEngine,
        confidenceDetails: result.processingMetadata.confidenceDetails,
        integrityAssessment: result.processingMetadata.integrityAssessment,
        qualityAssessment: result.processingMetadata.qualityAssessment,
      },
      counts: {
        extractedFields: result.extractedFields.length,
        reportSections: result.reportSections.length,
        issues: result.issues.length,
      },
    },
  };
}

export async function buildPublicBatchStatus(batch: PublicBatchRecord): Promise<PublicBatchStatusSnapshot> {
  const submissions = await listPublicBatchSubmissions(batch.id);
  const statuses = await Promise.all(submissions.map((submission) => buildPublicSubmissionStatus(submission)));
  const counts = {
    queued: statuses.filter((entry) => entry.status === "queued").length,
    processing: statuses.filter((entry) => entry.status === "processing").length,
    completed: statuses.filter((entry) => entry.status === "completed").length,
    review: statuses.filter((entry) => entry.status === "review").length,
    rejected: statuses.filter((entry) => entry.status === "rejected").length,
    failed: statuses.filter((entry) => entry.status === "failed").length,
  };

  let status: PublicBatchStatus = "queued";
  if (counts.processing > 0 || counts.queued > 0) {
    status = counts.processing > 0 ? "processing" : "queued";
  } else if (counts.failed === statuses.length && statuses.length > 0) {
    status = "failed";
  } else if (counts.review === 0 && counts.rejected === 0 && counts.failed === 0) {
    status = "completed";
  } else {
    status = "partial";
  }

  return {
    batchId: batch.id,
    externalId: batch.externalId,
    tenantId: batch.tenantId,
    source: batch.source,
    status,
    createdAt: batch.createdAt,
    updatedAt: batch.updatedAt,
    callbackUrl: batch.callbackUrl,
    itemCount: statuses.length,
    queued: counts.queued,
    processing: counts.processing,
    completed: counts.completed,
    review: counts.review,
    rejected: counts.rejected,
    failed: counts.failed,
    lastWebhookDelivery: batch.lastWebhookDelivery,
  };
}

export async function notifyPublicSubmissionProcessed(document: DocumentRecord) {
  const submission = await getPublicSubmissionByDocumentId(document.id);
  if (!submission) return null;

  const status = derivePublicSubmissionStatus(document);
  if (!terminalSubmissionStatus(status)) return null;
  await recordSubmissionUsage(submission, document, status);

  if (!submission.callbackUrl) {
    if (submission.batchId) {
      await notifyPublicBatchIfTerminal(submission.batchId);
    }
    return null;
  }

  const eventType = eventTypeForSubmissionStatus(status);
  if (submission.lastWebhookDelivery?.eventType === eventType && submission.lastWebhookDelivery.status === "delivered") {
    return submission.lastWebhookDelivery;
  }

  await enqueuePublicWebhook({
    submissionId: submission.id,
    batchId: submission.batchId,
    apiClientId: submission.apiClientId,
    tenantId: submission.tenantId,
    source: "submission",
    targetUrl: submission.callbackUrl,
    eventType,
    dedupeKey: `submission:${submission.id}:${eventType}`,
  });
  const deliveries = await drainPublicWebhookQueue(buildWebhookPayloadForLog, { apiClientId: submission.apiClientId, limit: 5 });
  const delivery = deliveries.find((entry) => entry.eventType === eventType && entry.source === "submission") ?? null;

  if (submission.batchId) {
    await notifyPublicBatchIfTerminal(submission.batchId);
  }

  return delivery;
}

export async function notifyPublicBatchIfTerminal(batchId: string) {
  const batch = await getPublicBatchById(batchId);
  if (!batch) return null;
  if (batch.submissionIds.length === 0) return null;

  const snapshot = await buildPublicBatchStatus(batch);
  const submissions = await listPublicBatchSubmissions(batchId);
  if (submissions.length !== batch.submissionIds.length) return null;
  if (!terminalBatchStatus(snapshot.status)) return null;
  await recordBatchUsage(batch, snapshot);

  if (!batch.callbackUrl) {
    return null;
  }

  const eventType = eventTypeForBatchStatus(snapshot.status);
  if (batch.lastWebhookDelivery?.eventType === eventType && batch.lastWebhookDelivery.status === "delivered") {
    return batch.lastWebhookDelivery;
  }

  await enqueuePublicWebhook({
    submissionId: null,
    batchId: batch.id,
    apiClientId: batch.apiClientId,
    tenantId: batch.tenantId,
    source: "batch",
    targetUrl: batch.callbackUrl,
    eventType,
    dedupeKey: `batch:${batch.id}:${eventType}`,
  });
  const deliveries = await drainPublicWebhookQueue(buildWebhookPayloadForLog, { apiClientId: batch.apiClientId, limit: 5 });
  const delivery = deliveries.find((entry) => entry.eventType === eventType && entry.source === "batch") ?? null;
  return delivery;
}

export async function getPublicSubmissionOrThrow(submissionId: string) {
  const submission = await getPublicSubmissionById(submissionId);
  return submission;
}

export async function deliverQueuedPublicWebhooks(options?: { apiClientId?: string; limit?: number }) {
  return drainPublicWebhookQueue(buildWebhookPayloadForLog, options);
}

export async function retryPublicWebhookDelivery(logId: string) {
  const queued = await requeuePublicWebhookLog(logId);
  if (!queued) return null;
  const payload = await buildWebhookPayloadForLog(queued);
  return attemptWebhookDelivery(queued, payload);
}

export async function getPublicWebhookLog(logId: string) {
  return getWebhookLogById(logId);
}
