import type {
  DocumentDecision,
  DocumentRecord,
  DocumentStatus,
  ProcessingJobRecord,
  ProcessingStageName,
  ProcessingStageRecord
} from "@ocr/shared";
import { createHmac } from "node:crypto";
import { createDefaultProcessingStages, createExtractedFieldsFromSections, createJobSnapshot, normalizeDocumentRecord } from "@/lib/document-record";
import { buildWebhookPayload } from "@/lib/document-export";
import { getAllDocuments, getDocumentById, getDocumentByIdInternal, updateDocument } from "@/lib/document-store";
import { recordOpsAuditEvent } from "@/lib/ops-audit";
import { shouldRedactExternalPayloads } from "@/lib/pii";
import { deliverQueuedPublicWebhooks, notifyPublicSubmissionProcessed } from "@/lib/public-api-status";
import { resolveAdaptiveRoutingStrategy } from "@/lib/routing-benchmark";
import { isWebFeatureEnabled } from "@/lib/runtime-flags";
import { resolveTenantProcessingOptions } from "@/lib/tenant-processing";
import { buildProcessedMockDocument } from "@/lib/mock-pipeline";
import { runRemoteProcessing } from "@/lib/ocr-api";
import { buildReportHtml } from "@/lib/report-html";

const DEFAULT_MAX_ATTEMPTS = 3;
const BASE_RETRY_DELAY_MS = 60_000;
const DEFAULT_JOB_LEASE_MS = 120_000;

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

type WebhookDelivery = {
  enabled: boolean;
  eventType: string | null;
  attemptedAt: string | null;
  status: "disabled" | "delivered" | "failed";
  responseStatus: number | null;
  error: string | null;
  attemptCount?: number;
};

export type WorkerRunSummary = {
  requested: number;
  processed: number;
  completed: number;
  failed: number;
  sentToDlq: number;
  review: number;
  autoAccepted: number;
  acceptWithWarning: number;
  routingStrategies: string[];
};

function nowIso() {
  return new Date().toISOString();
}

function resolveEngineLabel() {
  return process.env.OCR_API_URL ? "fastapi-remote" : "mock-pipeline";
}

function resolveWorkerId() {
  return process.env.OCR_WORKER_ID?.trim() || `worker-${process.pid}`;
}

function resolveJobLeaseMs() {
  const parsed = Number.parseInt(process.env.OCR_JOB_LEASE_MS ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_JOB_LEASE_MS;
}

function resolveRoutingOverrides(document: DocumentRecord) {
  const tenantOptions = resolveTenantProcessingOptions(document);
  const adaptiveDecision = isWebFeatureEnabled("adaptiveRouting")
    ? resolveAdaptiveRoutingStrategy(document)
    : {
        strategy: {
          name: "tenant_default",
          label: "Tenant default",
          description: "Usa solamente defaults del tenant y del runtime.",
          visualEngine: null,
          ensembleMode: null,
          ensembleEngines: null,
          fieldAdjudicationMode: null,
          structuredMode: null,
        },
        reasons: ["Adaptive routing deshabilitado por feature flag; se usan defaults del tenant/runtime."],
      };
  const strategy = adaptiveDecision.strategy;

  return {
    visualEngine: tenantOptions.visualEngine && tenantOptions.visualEngine !== "auto" ? tenantOptions.visualEngine : (strategy.visualEngine ?? tenantOptions.visualEngine),
    decisionProfile: tenantOptions.decisionProfile,
    structuredMode: tenantOptions.structuredMode && tenantOptions.structuredMode !== "auto" ? tenantOptions.structuredMode : (strategy.structuredMode ?? tenantOptions.structuredMode),
    ensembleMode: tenantOptions.ensembleMode ?? strategy.ensembleMode,
    ensembleEngines: tenantOptions.ensembleEngines ?? strategy.ensembleEngines,
    fieldAdjudicationMode: tenantOptions.fieldAdjudicationMode ?? strategy.fieldAdjudicationMode,
    routingStrategy: strategy.name,
    routingReasons: adaptiveDecision.reasons,
  };
}

function getWebhookConfig() {
  return {
    url: process.env.OCR_RESULT_WEBHOOK_URL,
    secret: process.env.OCR_RESULT_WEBHOOK_SECRET ?? null,
    maxAttempts: Math.max(1, Number.parseInt(process.env.OCR_RESULT_WEBHOOK_MAX_ATTEMPTS ?? "3", 10) || 3),
    baseDelayMs: Math.max(250, Number.parseInt(process.env.OCR_RESULT_WEBHOOK_BASE_DELAY_MS ?? "1000", 10) || 1000)
  };
}

function buildIdempotencyKey(document: DocumentRecord) {
  return [document.id, document.sourceHash ?? "no-hash", document.documentFamily, document.country, document.variant ?? "no-variant"].join(":");
}

function mapDecisionToStatus(decision: DocumentDecision): DocumentStatus {
  if (decision === "reject") return "rejected";
  if (decision === "human_review") return "review";
  return "completed";
}

export function hasMaterializedProcessingResult(document: DocumentRecord | null) {
  if (!document) return false;
  return Boolean(
    document.processedAt &&
      document.decision !== "pending" &&
      document.globalConfidence !== null &&
      document.extractedFields.length > 0 &&
      document.reportSections.length > 0
  );
}

function cloneStages(stages: ProcessingStageRecord[] | undefined) {
  return (stages && stages.length > 0 ? stages : createDefaultProcessingStages()).map((stage) => ({ ...stage }));
}

function updateStage(stages: ProcessingStageRecord[], name: ProcessingStageName, patch: Partial<ProcessingStageRecord>) {
  return stages.map((stage) => (stage.name === name ? { ...stage, ...patch } : stage));
}

function completePendingStages(stages: ProcessingStageRecord[], stageNames: ProcessingStageName[]) {
  const timestamp = nowIso();
  return stages.map((stage) =>
    stageNames.includes(stage.name) && stage.status === "pending"
      ? {
          ...stage,
          status: "completed" as const,
          startedAt: stage.startedAt ?? timestamp,
          finishedAt: timestamp,
          message: stage.message ?? "Etapa completada por el orquestador."
        }
      : stage
  );
}

function buildQueuedJob(document: DocumentRecord, existingJob: ProcessingJobRecord | null, engine: string) {
  const timestamp = nowIso();
  const idempotencyKey = buildIdempotencyKey(document);
  const routing = resolveRoutingOverrides(document);

  if (existingJob?.status === "failed") {
    return {
      ...existingJob,
      status: "queued" as const,
      engine,
      errorMessage: null,
      nextRetryAt: null,
      queueName: "default",
      idempotencyKey,
      currentStage: null,
      leaseOwner: null,
      leaseExpiresAt: null,
        payload: {
          documentId: document.id,
          filename: document.filename,
          requestedFamily: document.documentFamily,
          requestedCountry: document.country,
          decisionProfile: routing.decisionProfile,
          requestedVisualEngine: routing.visualEngine,
          structuredMode: routing.structuredMode,
          ensembleMode: routing.ensembleMode,
          ensembleEngines: routing.ensembleEngines,
          fieldAdjudicationMode: routing.fieldAdjudicationMode,
          routingStrategy: routing.routingStrategy,
          routingReasons: routing.routingReasons,
        },
      result: null,
      stages: cloneStages(existingJob.stages),
      createdAt: existingJob.createdAt ?? timestamp
    };
  }

  return createJobSnapshot({
    status: "queued",
    engine,
    createdAt: timestamp,
    maxAttempts: DEFAULT_MAX_ATTEMPTS,
    idempotencyKey,
    queueName: "default",
      payload: {
        documentId: document.id,
        filename: document.filename,
        requestedFamily: document.documentFamily,
        requestedCountry: document.country,
        decisionProfile: routing.decisionProfile,
        requestedVisualEngine: routing.visualEngine,
        structuredMode: routing.structuredMode,
        ensembleMode: routing.ensembleMode,
        ensembleEngines: routing.ensembleEngines,
        fieldAdjudicationMode: routing.fieldAdjudicationMode,
        routingStrategy: routing.routingStrategy,
        routingReasons: routing.routingReasons,
      },
      stages: createDefaultProcessingStages()
    });
}

function shouldSkipDuplicateQueue(document: DocumentRecord, idempotencyKey: string) {
  const latestJob = document.latestJob;
  if (!latestJob) return false;
  if (latestJob.idempotencyKey !== idempotencyKey) return false;

  if (latestJob.status === "queued") {
    return true;
  }

  if (latestJob.status === "running") {
    return hasActiveLease(latestJob);
  }

  if (latestJob.status === "completed" && document.processedAt) {
    return new Date(document.updatedAt).getTime() <= new Date(document.processedAt).getTime();
  }

  return false;
}

function startJobRun(job: ProcessingJobRecord | null, engine: string, document: DocumentRecord): ProcessingJobRecord {
  const timestamp = nowIso();
  const current = job ?? buildQueuedJob(document, null, engine);
  const workerId = resolveWorkerId();
  let stages = cloneStages(current.stages);

  stages = updateStage(stages, "ingest", {
    status: "completed",
    startedAt: stages.find((stage) => stage.name === "ingest")?.startedAt ?? timestamp,
    finishedAt: timestamp,
    message: "Documento tomado desde la cola y preparado para procesamiento."
  });
  stages = updateStage(stages, "classify", {
    status: "running",
    startedAt: timestamp,
    finishedAt: null,
    message: "Clasificando documento y resolviendo el pipeline activo."
  });

  return {
    ...current,
    status: "running",
    engine,
    startedAt: timestamp,
    finishedAt: null,
    errorMessage: null,
    attemptCount: current.attemptCount + 1,
    nextRetryAt: null,
    queueName: "default",
    currentStage: "classify",
    leaseOwner: workerId,
    leaseExpiresAt: new Date(Date.now() + resolveJobLeaseMs()).toISOString(),
    stages
  };
}

function buildSuccessResult(document: DocumentRecord) {
  return {
    decision: document.decision,
    status: document.status,
    documentFamily: document.documentFamily,
    country: document.country,
    variant: document.variant,
    globalConfidence: document.globalConfidence,
    reviewRequired: document.reviewRequired,
    packId: document.processingMetadata.packId,
    engine: document.processingMetadata.processingEngine
  } satisfies Record<string, unknown>;
}

function summarizeWorkerResults(processed: DocumentRecord[], requested: number): WorkerRunSummary {
  const routingStrategies = [...new Set(processed.map((document) => document.processingMetadata.routingStrategy).filter((value): value is string => Boolean(value)))];
  return {
    requested,
    processed: processed.length,
    completed: processed.filter((document) => document.latestJob?.status === "completed").length,
    failed: processed.filter((document) => document.latestJob?.status === "failed").length,
    sentToDlq: processed.filter((document) => document.latestJob?.queueName === "dlq").length,
    review: processed.filter((document) => document.decision === "human_review").length,
    autoAccepted: processed.filter((document) => document.decision === "auto_accept").length,
    acceptWithWarning: processed.filter((document) => document.decision === "accept_with_warning").length,
    routingStrategies,
  };
}

function resolveWebhookEventType(document: DocumentRecord) {
  if (document.decision === "reject") return "document.rejected";
  if (document.reviewRequired) return "document.review_required";
  return "document.completed";
}

async function deliverResultWebhook(document: DocumentRecord, eventType: string, extra?: Record<string, unknown>): Promise<WebhookDelivery> {
  const { url, secret, maxAttempts, baseDelayMs } = getWebhookConfig();

  if (!url) {
    return {
      enabled: false,
      eventType: null,
      attemptedAt: null,
      status: "disabled",
      responseStatus: null,
      error: null,
    };
  }

  const attemptedAt = nowIso();
  const payload = buildWebhookPayload(document, eventType, extra, { redacted: shouldRedactExternalPayloads() });
  const body = JSON.stringify(payload);
  const headers: Record<string, string> = {
    "content-type": "application/json",
    "x-ocr-event": eventType,
    "x-ocr-delivered-at": attemptedAt,
  };

  if (secret) {
    headers["x-ocr-signature"] = createHmac("sha256", secret).update(body).digest("hex");
  }

  let responseStatus: number | null = null;
  let errorMessage: string | null = null;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      const response = await fetch(url, {
        method: "POST",
        headers,
        body,
        cache: "no-store"
      });
      responseStatus = response.status;
      if (response.ok) {
        return {
          enabled: true,
          eventType,
          attemptedAt,
          status: "delivered",
          responseStatus,
          error: null,
          attemptCount: attempt,
        };
      }
      errorMessage = `Webhook returned ${response.status}`;
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : "Unexpected webhook delivery error";
    }

    if (attempt < maxAttempts) {
      await sleep(baseDelayMs * Math.max(1, 2 ** (attempt - 1)));
    }
  }

  return {
    enabled: true,
    eventType,
    attemptedAt,
    status: "failed",
    responseStatus,
    error: errorMessage,
    attemptCount: maxAttempts,
  };
}

function completeJobRun(job: ProcessingJobRecord | null, engine: string, document: DocumentRecord): ProcessingJobRecord {
  const timestamp = nowIso();
  const current = job ?? createJobSnapshot({ status: "completed", engine });
  let stages = cloneStages(current.stages);

  stages = updateStage(stages, "classify", {
    status: "completed",
    startedAt: stages.find((stage) => stage.name === "classify")?.startedAt ?? current.startedAt ?? timestamp,
    finishedAt: timestamp,
    message: "Clasificacion completada."
  });
  stages = completePendingStages(stages, ["extract", "normalize", "validate", "report"]);
  stages = updateStage(stages, "persist", {
    status: "completed",
    startedAt: stages.find((stage) => stage.name === "persist")?.startedAt ?? timestamp,
    finishedAt: timestamp,
    message: "Resultado persistido en el documento y en la fuente de jobs."
  });

  return {
    ...current,
    status: "completed",
    engine,
    finishedAt: timestamp,
    errorMessage: null,
    nextRetryAt: null,
    queueName: "default",
    currentStage: null,
    leaseOwner: null,
    leaseExpiresAt: null,
    result: buildSuccessResult(document),
    stages
  };
}

function computeNextRetryAt(attemptCount: number) {
  return new Date(Date.now() + BASE_RETRY_DELAY_MS * Math.max(1, 2 ** Math.max(0, attemptCount - 1))).toISOString();
}

function failJobRun(job: ProcessingJobRecord | null, engine: string, message: string): ProcessingJobRecord {
  const timestamp = nowIso();
  const current = job ?? createJobSnapshot({ status: "failed", engine, maxAttempts: DEFAULT_MAX_ATTEMPTS });
  const retryEligible = current.attemptCount < current.maxAttempts;
  const failedStage = current.currentStage ?? "classify";
  let stages = cloneStages(current.stages);

  stages = updateStage(stages, failedStage, {
    status: "failed",
    startedAt: stages.find((stage) => stage.name === failedStage)?.startedAt ?? current.startedAt ?? timestamp,
    finishedAt: timestamp,
    message
  });

  return {
    ...current,
    status: "failed",
    engine,
    finishedAt: timestamp,
    errorMessage: message,
    nextRetryAt: retryEligible ? computeNextRetryAt(current.attemptCount) : null,
    queueName: retryEligible ? "retry" : "dlq",
    leaseOwner: null,
    leaseExpiresAt: null,
    result: {
      retryEligible,
      failedStage,
      errorMessage: message,
      failureCount: current.attemptCount
    },
    stages
  };
}

function isRetryDue(job: ProcessingJobRecord | null) {
  if (!job || job.status !== "failed") return false;
  if (job.attemptCount >= job.maxAttempts) return false;
  if (!job.nextRetryAt) return true;
  return new Date(job.nextRetryAt).getTime() <= Date.now();
}

function hasActiveLease(job: ProcessingJobRecord | null) {
  if (!job?.leaseExpiresAt) return false;
  return new Date(job.leaseExpiresAt).getTime() > Date.now();
}

function withPipelineError(current: DocumentRecord, message: string, job: ProcessingJobRecord) {
  const duplicateIssue = current.issues.some((issue) => issue.type === "PIPELINE_ERROR" && issue.message === message);
  return {
    ...current,
    status: "review" as const,
    decision: "human_review" as const,
    reviewRequired: true,
    latestJob: job,
    updatedAt: nowIso(),
    issues: duplicateIssue
      ? current.issues
      : [
          ...current.issues,
          {
            id: crypto.randomUUID(),
            type: "PIPELINE_ERROR",
            field: "system",
            severity: "high" as const,
            message,
            suggestedAction:
              job.queueName === "retry"
                ? `El job se reintentara automaticamente en ${job.nextRetryAt ?? "la siguiente ventana"}.`
                : "Revisar el engine configurado o reenviar el caso a la cola despues de corregir la causa raiz."
          }
        ]
  };
}

export async function enqueueDocumentProcessing(documentId: string, options?: { force?: boolean }) {
  const document = await getDocumentByIdInternal(documentId);

  if (!document) {
    return null;
  }

  const engine = resolveEngineLabel();
  const idempotencyKey = buildIdempotencyKey(document);

  if (!options?.force && shouldSkipDuplicateQueue(document, idempotencyKey)) {
    return document;
  }

  const queued = await updateDocument(documentId, (current) => ({
    ...current,
    status: "processing",
    latestJob: buildQueuedJob(current, current.latestJob, engine),
    updatedAt: nowIso()
  }));

  if (queued) {
    await recordOpsAuditEvent({
      action: "processing.queued",
      tenantId: queued.tenantId,
      documentId: queued.id,
      payload: {
        engine,
        force: options?.force ?? false,
        idempotencyKey,
      },
    })
  }

  return queued
}

export async function processDocumentJob(documentId: string) {
  const document = await getDocumentByIdInternal(documentId);

  if (!document) {
    return null;
  }

  if (document.latestJob?.status === "running" && hasActiveLease(document.latestJob)) {
    return document;
  }

  const engine = resolveEngineLabel();

  await updateDocument(documentId, (current) => ({
    ...current,
    status: "processing",
    latestJob: startJobRun(current.latestJob, engine, current),
    updatedAt: nowIso()
  }));

  const freshDocument = await getDocumentByIdInternal(documentId);

  if (!freshDocument) {
    return null;
  }

  await recordOpsAuditEvent({
    action: "processing.started",
    tenantId: freshDocument.tenantId,
    documentId: freshDocument.id,
    payload: {
      engine,
      jobId: freshDocument.latestJob?.id ?? null,
    },
  })

  try {
    const routing = resolveRoutingOverrides(freshDocument);
    const remote = await runRemoteProcessing(freshDocument, {
      visualEngine: routing.visualEngine,
      decisionProfile: routing.decisionProfile,
      structuredMode: routing.structuredMode,
      ensembleMode: routing.ensembleMode,
      ensembleEngines: routing.ensembleEngines,
      fieldAdjudicationMode: routing.fieldAdjudicationMode,
    });
    const baseProcessed = remote
      ? {
          ...freshDocument,
          ...remote
        }
      : buildProcessedMockDocument(freshDocument);

    const normalized = normalizeDocumentRecord(baseProcessed);
    const completedJob = completeJobRun(freshDocument.latestJob, engine, normalized);

    const draftDocument: DocumentRecord = {
      ...normalized,
      status: mapDecisionToStatus(normalized.decision),
      processedAt: nowIso(),
      updatedAt: nowIso(),
      extractedFields:
        normalized.extractedFields.length > 0
          ? normalized.extractedFields
          : createExtractedFieldsFromSections(normalized.reportSections, normalized.issues, engine),
      latestJob: completedJob,
      reportHtml: normalized.reportHtml ?? buildReportHtml(normalized),
      processingMetadata: {
        ...normalized.processingMetadata,
        routingStrategy: routing.routingStrategy,
        routingReasons: routing.routingReasons,
        processingEngine: normalized.processingMetadata.processingEngine ?? engine
      }
    };

    const webhookDelivery = await deliverResultWebhook(draftDocument, resolveWebhookEventType(draftDocument));
    const finalDocument: DocumentRecord = {
      ...draftDocument,
      latestJob: {
        ...completedJob,
        result: {
          ...(completedJob.result ?? {}),
          webhook: webhookDelivery
        }
      }
    };

    const persisted = await updateDocument(documentId, () => finalDocument);
    if (persisted) {
      await notifyPublicSubmissionProcessed(persisted);
      await recordOpsAuditEvent({
        action: "processing.completed",
        tenantId: persisted.tenantId,
        documentId: persisted.id,
        payload: {
          engine,
          decision: persisted.decision,
          packId: persisted.processingMetadata.packId,
          routingStrategy: persisted.processingMetadata.routingStrategy,
          routingReasons: persisted.processingMetadata.routingReasons,
          trace: persisted.processingMetadata.processingTrace,
        },
      })
    }
    return persisted
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unexpected pipeline error";

    const failedDocument = await updateDocument(documentId, (current) => {
      const failedJob = failJobRun(current.latestJob, engine, message);
      return withPipelineError(current, message, failedJob);
    });

    if (!failedDocument) {
      return null;
    }

    const webhookDelivery = await deliverResultWebhook(failedDocument, "document.failed", {
      errorMessage: message
    });

    const persisted = await updateDocument(documentId, (current) => ({
      ...current,
      latestJob: current.latestJob
        ? {
            ...current.latestJob,
            result: {
              ...(current.latestJob.result ?? {}),
              webhook: webhookDelivery
            }
          }
        : current.latestJob
    }));
    if (persisted) {
      await notifyPublicSubmissionProcessed(persisted);
      await recordOpsAuditEvent({
        action: "processing.failed",
        tenantId: persisted.tenantId,
        documentId: persisted.id,
        payload: {
          engine,
          errorMessage: message,
          queueName: persisted.latestJob?.queueName ?? null,
        },
      })
    }
    return persisted
  }
}

export async function finalizeProcessedDocument(documentId: string, currentDocument?: DocumentRecord | null) {
  const current = currentDocument ?? (await getDocumentByIdInternal(documentId));
  if (!current) {
    return null;
  }

  if (hasMaterializedProcessingResult(current)) {
    return current;
  }

  const routing = resolveRoutingOverrides(current);
  const remote = await runRemoteProcessing(current, {
    visualEngine: routing.visualEngine,
    decisionProfile: routing.decisionProfile,
    structuredMode: routing.structuredMode,
    ensembleMode: routing.ensembleMode,
    ensembleEngines: routing.ensembleEngines,
    fieldAdjudicationMode: routing.fieldAdjudicationMode,
  });

  const normalized = normalizeDocumentRecord({
    ...current,
    ...(remote ?? buildProcessedMockDocument(current)),
  });

  const finalized: DocumentRecord = {
    ...normalized,
    status: mapDecisionToStatus(normalized.decision),
    processedAt: normalized.processedAt ?? nowIso(),
    updatedAt: nowIso(),
    reportHtml: normalized.reportHtml ?? buildReportHtml(normalized),
  };

  return updateDocument(documentId, () => finalized);
}

export async function getQueuedDocuments() {
  const documents = await getAllDocuments();
  return documents.filter((document) => document.latestJob?.status === "queued" && !hasActiveLease(document.latestJob));
}

export async function getRetryableFailedDocuments() {
  const documents = await getAllDocuments();
  return documents.filter((document) => isRetryDue(document.latestJob) && !hasActiveLease(document.latestJob));
}

export async function getDlqDocuments() {
  const documents = await getAllDocuments();
  return documents.filter((document) => document.latestJob?.queueName === "dlq");
}

export async function requeueDlqJobs(limit = 10) {
  const dlqDocuments = (await getDlqDocuments()).slice(0, Math.max(1, limit));
  const requeued: DocumentRecord[] = [];

  for (const document of dlqDocuments) {
    const updated = await updateDocument(document.id, (current) => {
      if (!current.latestJob || current.latestJob.queueName !== "dlq") {
        return current;
      }

      return {
        ...current,
        status: "processing",
        updatedAt: nowIso(),
        latestJob: buildQueuedJob(current, current.latestJob, resolveEngineLabel()),
      };
    });

    if (updated) {
      requeued.push(updated);
      await recordOpsAuditEvent({
        action: "processing.requeue_dlq",
        tenantId: updated.tenantId,
        documentId: updated.id,
        payload: {
          queueName: "dlq",
          routingStrategy: updated.processingMetadata.routingStrategy,
        },
      });
    }
  }

  return requeued;
}

export async function runQueuedJobs(limit = 1, options?: { includeRetries?: boolean; concurrency?: number }) {
  const queuedDocuments = await getQueuedDocuments();
  const retryableDocuments = options?.includeRetries ? await getRetryableFailedDocuments() : [];
  const selected = [...queuedDocuments, ...retryableDocuments].slice(0, Math.max(1, limit));
  const processed: DocumentRecord[] = [];

  const concurrency = Math.max(1, Math.min(options?.concurrency ?? 1, selected.length || 1));
  let cursor = 0;
  const workers = Array.from({ length: concurrency }, async () => {
    while (cursor < selected.length) {
      const currentIndex = cursor;
      cursor += 1;
      const document = selected[currentIndex];
      const result = await processDocumentJob(document.id);
      if (result) {
        processed.push(result);
      }
    }
  });

  await Promise.all(workers);

  return processed;
}

export async function runWorkerCycle(limit = 10, options?: { concurrency?: number }) {
  const processed = await runQueuedJobs(limit, { includeRetries: true, concurrency: options?.concurrency });
  await deliverQueuedPublicWebhooks({ limit: Math.max(5, limit) });
  const summary = summarizeWorkerResults(processed, Math.max(1, limit));
  await recordOpsAuditEvent({
    action: "processing.worker_cycle",
    payload: summary,
  });
  return { processed, summary };
}
