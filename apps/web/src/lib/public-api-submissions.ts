import { AUTO_COUNTRY_CODE, type DocumentFamily, type DocumentRecord } from "@ocr/shared";

import { getPublicApiLimits, normalizeRequestedDocumentFamily, normalizeRequestedProcessingMode } from "@/lib/public-api-auth";
import { createDocumentFromUpload } from "@/lib/document-store";
import { enqueueDocumentProcessing, processDocumentJob } from "@/lib/document-processing";
import { recordOpsAuditEvent } from "@/lib/ops-audit";
import { createPublicBatch, createPublicSubmission, recordUsageLedgerEvent, updatePublicBatch } from "@/lib/public-api-store";
import { normalizeCallbackUrl, normalizeManifestFileUrl } from "@/lib/public-api-security";
import { buildPublicBatchStatus, buildPublicSubmissionResult, buildPublicSubmissionStatus, notifyPublicBatchIfTerminal } from "@/lib/public-api-status";
import { resolveOrProvisionPublicApiTenantId } from "@/lib/public-api-tenants";
import { derivePublicSubmissionStatus, type PublicApiClient, type PublicBatchRecord, type PublicBatchSource, type PublicSubmissionRecord, type PublicSubmissionResult, type PublicSubmissionSource, type PublicSubmissionStatusSnapshot } from "@/lib/public-api-types";

type SubmissionInput = {
  client: PublicApiClient;
  file: File;
  documentFamily: DocumentFamily;
  country: string;
  externalId?: string | null;
  callbackUrl?: string | null;
  metadata?: Record<string, unknown>;
  processingMode?: "sync" | "queue";
  batchId?: string | null;
  source?: PublicSubmissionSource;
};

type ManifestItem = {
  fileUrl: string;
  filename?: string | null;
  documentFamily?: DocumentFamily;
  country?: string | null;
  externalId?: string | null;
  metadata?: Record<string, unknown>;
};

type SubmissionCreationOptions = {
  forceProcessingMode?: "sync" | "queue" | null;
  allowCallbacks?: boolean;
  augmentMetadata?: Record<string, unknown>;
};

function isAllowedMimeType(mimeType: string) {
  const limits = getPublicApiLimits();
  return limits.allowedMimeTypes.includes(mimeType as (typeof limits.allowedMimeTypes)[number]);
}

function hasAllowedExtension(filename: string) {
  const normalized = filename.toLowerCase();
  return [".pdf", ".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff"].some((suffix) => normalized.endsWith(suffix));
}

function normalizeCountry(value: FormDataEntryValue | string | null | undefined) {
  return ((typeof value === "string" ? value : AUTO_COUNTRY_CODE) || AUTO_COUNTRY_CODE).trim().toUpperCase() || AUTO_COUNTRY_CODE;
}

function parseOptionalJson(raw: FormDataEntryValue | string | null | undefined): Record<string, unknown> {
  if (!raw || typeof raw !== "string") return {};
  try {
    const parsed = JSON.parse(raw) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function ensureAcceptedFile(file: File, totalBytes = file.size) {
  const limits = getPublicApiLimits();
  if (!isAllowedMimeType(file.type || "application/octet-stream") && !hasAllowedExtension(file.name)) {
    throw new Error(`Unsupported file type: ${file.type || "application/octet-stream"}`);
  }
  if (file.size > limits.maxSingleFileBytes) {
    throw new Error(`File exceeds max size of ${limits.maxSingleFileBytes} bytes.`);
  }
  if (totalBytes > limits.maxBatchBytes) {
    throw new Error(`Batch exceeds max total size of ${limits.maxBatchBytes} bytes.`);
  }
}

async function createSubmissionRecord(input: SubmissionInput) {
  ensureAcceptedFile(input.file);
  const resolvedTenantId = await resolveOrProvisionPublicApiTenantId(input.client.tenantId);
  const document = await createDocumentFromUpload({
    file: input.file,
    documentFamily: input.documentFamily,
    country: input.country,
    tenantId: resolvedTenantId,
  });
  const submission = await createPublicSubmission({
    documentId: document.id,
    batchId: input.batchId ?? null,
    apiClientId: input.client.id,
    tenantId: document.tenantId,
    externalId: input.externalId ?? null,
    callbackUrl: input.callbackUrl ?? null,
    metadata: input.metadata ?? {},
    filename: document.filename,
    mimeType: document.mimeType,
    size: document.size,
    documentFamily: document.documentFamily,
    country: document.country,
    processingMode: input.processingMode ?? getPublicApiLimits().defaultProcessingMode,
    source: input.source ?? "upload",
  });

  await recordUsageLedgerEvent({
    dedupeKey: `submission-created:${submission.id}`,
    apiClientId: input.client.id,
    tenantId: document.tenantId,
    submissionId: submission.id,
    batchId: submission.batchId,
    documentId: document.id,
    eventType: "submission.created",
    documentFamily: document.documentFamily,
    country: document.country,
    decision: null,
    status: "queued",
    units: 1,
    bytes: document.size,
    latencyMs: null,
    metadata: {
      processingMode: submission.processingMode,
      source: submission.source,
      callbackConfigured: Boolean(submission.callbackUrl),
    },
  });

  await enqueueDocumentProcessing(document.id, { force: true });
  const processed = submission.processingMode === "sync" ? await processDocumentJob(document.id) : null;

  await recordOpsAuditEvent({
    action: "public_api.submission_created",
    tenantId: document.tenantId,
    documentId: document.id,
    payload: {
      submissionId: submission.id,
      batchId: submission.batchId,
      apiClientId: input.client.id,
      processingMode: submission.processingMode,
      externalId: submission.externalId,
    },
  });

  return {
    submission,
    document: processed ?? document,
  };
}

function buildInlineSubmissionStatus(submission: PublicSubmissionRecord, document: DocumentRecord): PublicSubmissionStatusSnapshot {
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
    latestDecision: document.decision,
    globalConfidence: document.globalConfidence,
    reviewRequired: document.reviewRequired,
    processedAt: document.processedAt,
  };
}

function buildInlineSubmissionResult(submission: PublicSubmissionRecord, document: DocumentRecord): PublicSubmissionResult {
  return {
    submissionId: submission.id,
    externalId: submission.externalId,
    status: derivePublicSubmissionStatus(document),
    filename: submission.filename,
    documentId: submission.documentId,
    documentFamily: document.documentFamily,
    country: document.country,
    decision: document.decision,
    globalConfidence: document.globalConfidence,
    reviewRequired: document.reviewRequired,
    processedAt: document.processedAt,
    resultUrl: `/api/public/v1/submissions/${submission.id}/result`,
    callbackUrl: submission.callbackUrl,
  };
}

async function fetchManifestFile(item: ManifestItem) {
  const manifestUrl = normalizeManifestFileUrl(item.fileUrl);
  const response = await fetch(manifestUrl, { method: "GET", cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Could not fetch manifest file: ${manifestUrl}`);
  }
  const contentType = response.headers.get("content-type") ?? "application/octet-stream";
  const contentDisposition = response.headers.get("content-disposition") ?? "";
  const filenameFromHeader = /filename="?([^";]+)"?/i.exec(contentDisposition)?.[1] ?? null;
  const filename = item.filename ?? filenameFromHeader ?? new URL(manifestUrl).pathname.split("/").pop() ?? "documento.bin";
  const buffer = await response.arrayBuffer();
  return new File([buffer], filename, { type: contentType });
}

export async function createPublicSubmissionFromFormData(formData: FormData, client: PublicApiClient, options?: SubmissionCreationOptions) {
  const file = formData.get("file");
  if (!(file instanceof File)) {
    throw new Error("A valid file is required.");
  }

  const resolvedProcessingMode = options?.forceProcessingMode ?? normalizeRequestedProcessingMode(formData.get("processing_mode") ?? formData.get("processingMode"));
  const resolvedCallbackUrl = options?.allowCallbacks === false
    ? null
    : normalizeCallbackUrl(typeof formData.get("callback_url") === "string" ? (formData.get("callback_url") as string) : null);
  const metadata = {
    ...parseOptionalJson(formData.get("metadata")),
    ...(options?.augmentMetadata ?? {}),
  };

  const payload = await createSubmissionRecord({
    client,
    file,
    documentFamily: normalizeRequestedDocumentFamily(formData.get("document_family") ?? formData.get("documentFamily")),
    country: normalizeCountry(formData.get("country")),
    externalId: typeof formData.get("external_id") === "string" ? (formData.get("external_id") as string) : null,
    callbackUrl: resolvedCallbackUrl,
    metadata,
    processingMode: resolvedProcessingMode,
    source: "upload",
  });

  return {
    submission:
      payload.submission.processingMode === "sync" && payload.document.processedAt
        ? buildInlineSubmissionStatus(payload.submission, payload.document)
        : await buildPublicSubmissionStatus(payload.submission),
    result:
      payload.submission.processingMode === "sync" && payload.document.processedAt
        ? buildInlineSubmissionResult(payload.submission, payload.document)
        : await buildPublicSubmissionResult(payload.submission),
  };
}

export async function createPublicBatchFromFiles(input: {
  client: PublicApiClient;
  files: File[];
  documentFamily: DocumentFamily;
  country: string;
  externalId?: string | null;
  callbackUrl?: string | null;
  metadata?: Record<string, unknown>;
  processingMode?: "sync" | "queue";
}) {
  const limits = getPublicApiLimits();
  if (input.files.length === 0) {
    throw new Error("At least one file is required.");
  }
  if (input.files.length > limits.maxBatchItems) {
    throw new Error(`Batch exceeds max item count of ${limits.maxBatchItems}.`);
  }
  if ((input.processingMode ?? "queue") === "sync" && input.files.length > limits.maxSyncBatchItems) {
    throw new Error(`Sync batch exceeds max item count of ${limits.maxSyncBatchItems}.`);
  }

  const totalBytes = input.files.reduce((acc, file) => acc + file.size, 0);
  for (const file of input.files) {
    ensureAcceptedFile(file, totalBytes);
  }

  const batch = await createPublicBatch({
    apiClientId: input.client.id,
    tenantId: await resolveOrProvisionPublicApiTenantId(input.client.tenantId),
    externalId: input.externalId ?? null,
    callbackUrl: normalizeCallbackUrl(input.callbackUrl ?? null),
    metadata: input.metadata ?? {},
    source: "upload",
    submissionIds: [],
  });

  await recordUsageLedgerEvent({
    dedupeKey: `batch-created:${batch.id}`,
    apiClientId: input.client.id,
    tenantId: batch.tenantId,
    submissionId: null,
    batchId: batch.id,
    documentId: null,
    eventType: "batch.created",
    documentFamily: input.documentFamily,
    country: input.country,
    decision: null,
    status: "queued",
    units: input.files.length,
    bytes: totalBytes,
    latencyMs: null,
    metadata: {
      callbackConfigured: Boolean(batch.callbackUrl),
      processingMode: input.processingMode ?? "queue",
    },
  });

  const submissions: PublicSubmissionRecord[] = [];
  for (const file of input.files) {
    const created = await createSubmissionRecord({
      client: input.client,
      file,
      documentFamily: input.documentFamily,
      country: input.country,
      callbackUrl: normalizeCallbackUrl(input.callbackUrl ?? null),
      metadata: input.metadata ?? {},
      processingMode: input.processingMode ?? "queue",
      batchId: batch.id,
      source: "upload",
    });
    submissions.push(created.submission);
  }

  const finalizedBatch = await createPublicBatchReference(batch, submissions.map((submission) => submission.id));
  await notifyPublicBatchIfTerminal(finalizedBatch.id);
  return {
    batch: await buildPublicBatchStatus(finalizedBatch),
    items: await Promise.all(submissions.map((submission) => buildPublicSubmissionStatus(submission))),
  };
}

async function createPublicBatchReference(batch: PublicBatchRecord, submissionIds: string[]) {
  const updated = await updatePublicBatch(batch.id, (current) => ({
    ...current,
    submissionIds,
  }));
  return updated ?? batch;
}

export async function createPublicBatchFromManifest(input: {
  client: PublicApiClient;
  externalId?: string | null;
  callbackUrl?: string | null;
  metadata?: Record<string, unknown>;
  processingMode?: "sync" | "queue";
  defaults?: { documentFamily?: DocumentFamily; country?: string | null };
  items: ManifestItem[];
}) {
  const limits = getPublicApiLimits();
  if (input.items.length === 0) {
    throw new Error("Manifest batch requires at least one item.");
  }
  if (input.items.length > limits.maxManifestItems) {
    throw new Error(`Manifest batch exceeds max item count of ${limits.maxManifestItems}.`);
  }
  if ((input.processingMode ?? "queue") === "sync" && input.items.length > limits.maxSyncBatchItems) {
    throw new Error(`Sync manifest batch exceeds max item count of ${limits.maxSyncBatchItems}.`);
  }

  const batch = await createPublicBatch({
    apiClientId: input.client.id,
    tenantId: await resolveOrProvisionPublicApiTenantId(input.client.tenantId),
    externalId: input.externalId ?? null,
    callbackUrl: normalizeCallbackUrl(input.callbackUrl ?? null),
    metadata: input.metadata ?? {},
    source: "manifest",
    submissionIds: [],
  });

  await recordUsageLedgerEvent({
    dedupeKey: `manifest-batch-created:${batch.id}`,
    apiClientId: input.client.id,
    tenantId: batch.tenantId,
    submissionId: null,
    batchId: batch.id,
    documentId: null,
    eventType: "batch.created",
    documentFamily: input.defaults?.documentFamily ?? null,
    country: input.defaults?.country ?? null,
    decision: null,
    status: "queued",
    units: input.items.length,
    bytes: 0,
    latencyMs: null,
    metadata: {
      source: "manifest",
      callbackConfigured: Boolean(batch.callbackUrl),
      processingMode: input.processingMode ?? "queue",
    },
  });

  const submissions: PublicSubmissionRecord[] = [];
  for (const item of input.items) {
    const file = await fetchManifestFile(item);
    ensureAcceptedFile(file);
    const created = await createSubmissionRecord({
      client: input.client,
      file,
      documentFamily: item.documentFamily ?? input.defaults?.documentFamily ?? "unclassified",
      country: normalizeCountry(item.country ?? input.defaults?.country ?? AUTO_COUNTRY_CODE),
      externalId: item.externalId ?? null,
      callbackUrl: normalizeCallbackUrl(input.callbackUrl ?? null),
      metadata: item.metadata ?? {},
      processingMode: input.processingMode ?? "queue",
      batchId: batch.id,
      source: "manifest",
    });
    submissions.push(created.submission);
  }

  const finalizedBatch = await createPublicBatchReference(batch, submissions.map((submission) => submission.id));
  await notifyPublicBatchIfTerminal(finalizedBatch.id);
  return {
    batch: await buildPublicBatchStatus(finalizedBatch),
    items: await Promise.all(submissions.map((submission) => buildPublicSubmissionStatus(submission))),
  };
}
