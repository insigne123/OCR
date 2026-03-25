import type { DocumentDecision, DocumentFamily, DocumentRecord } from "@ocr/shared";

export type PublicApiProcessingMode = "sync" | "queue";

export type PublicSubmissionStatus = "queued" | "processing" | "completed" | "review" | "rejected" | "failed";

export type PublicBatchStatus = "queued" | "processing" | "completed" | "partial" | "failed";

export type PublicSubmissionSource = "upload" | "manifest";

export type PublicBatchSource = "upload" | "manifest";

export type PublicWebhookDelivery = {
  id?: string;
  attemptedAt: string;
  status: "pending" | "delivered" | "failed" | "dead_letter";
  responseStatus: number | null;
  error: string | null;
  eventType: string;
  attemptNumber?: number;
  nextRetryAt?: string | null;
  targetUrl?: string | null;
  source?: "submission" | "batch" | "document";
};

export type PublicWebhookLogRecord = {
  id: string;
  submissionId: string | null;
  batchId: string | null;
  apiClientId: string;
  tenantId: string;
  source: "submission" | "batch" | "document";
  targetUrl: string;
  eventType: string;
  status: "pending" | "delivered" | "failed" | "dead_letter";
  attemptCount: number;
  maxAttempts: number;
  nextRetryAt: string | null;
  createdAt: string;
  updatedAt: string;
  lastAttemptAt: string | null;
  deliveries: PublicWebhookDelivery[];
  dedupeKey: string;
};

export type UsageLedgerRecord = {
  id: string;
  dedupeKey: string;
  apiClientId: string;
  tenantId: string;
  submissionId: string | null;
  batchId: string | null;
  documentId: string | null;
  eventType: string;
  documentFamily: DocumentFamily | null;
  country: string | null;
  decision: DocumentDecision | null;
  status: PublicSubmissionStatus | PublicBatchStatus | null;
  units: number;
  bytes: number;
  latencyMs: number | null;
  metadata: Record<string, unknown>;
  createdAt: string;
};

export type PublicFeedbackCorrection = {
  fieldName: string;
  previousValue: string | null;
  newValue: string | null;
  reason: string;
};

export type PublicFeedbackRecord = {
  id: string;
  submissionId: string;
  documentId: string;
  apiClientId: string;
  tenantId: string;
  reviewerName: string;
  notes: string | null;
  decision: DocumentDecision | null;
  corrections: PublicFeedbackCorrection[];
  createdAt: string;
};

export type PublicApiClient = {
  id: string;
  name: string;
  tenantId: string;
  apiKey: string;
  accessMode?: "public" | "trial";
  documentLimit?: number | null;
  expiresAt?: string | null;
  allowCallbacks?: boolean;
  forceProcessingMode?: PublicApiProcessingMode | null;
};

export type TrialUsageSnapshot = {
  clientId: string;
  clientName: string;
  companyName: string;
  limit: number;
  used: number;
  remaining: number;
  expiresAt: string | null;
  processingMode: PublicApiProcessingMode;
};

export type PublicSubmissionRecord = {
  id: string;
  documentId: string;
  batchId: string | null;
  apiClientId: string;
  tenantId: string;
  externalId: string | null;
  callbackUrl: string | null;
  metadata: Record<string, unknown>;
  filename: string;
  mimeType: string;
  size: number;
  documentFamily: DocumentFamily;
  country: string;
  processingMode: PublicApiProcessingMode;
  source: PublicSubmissionSource;
  createdAt: string;
  updatedAt: string;
  lastWebhookDelivery: PublicWebhookDelivery | null;
};

export type PublicBatchRecord = {
  id: string;
  apiClientId: string;
  tenantId: string;
  externalId: string | null;
  callbackUrl: string | null;
  metadata: Record<string, unknown>;
  source: PublicBatchSource;
  createdAt: string;
  updatedAt: string;
  submissionIds: string[];
  lastWebhookDelivery: PublicWebhookDelivery | null;
};

export type PublicSubmissionResult = {
  submissionId: string;
  externalId: string | null;
  status: PublicSubmissionStatus;
  filename: string;
  documentId: string;
  documentFamily: DocumentFamily;
  country: string;
  decision: DocumentDecision;
  globalConfidence: number | null;
  reviewRequired: boolean;
  processedAt: string | null;
  resultUrl: string;
  callbackUrl: string | null;
};

export type PublicSubmissionStatusSnapshot = {
  submissionId: string;
  externalId: string | null;
  documentId: string;
  batchId: string | null;
  status: PublicSubmissionStatus;
  filename: string;
  mimeType: string;
  size: number;
  documentFamily: DocumentFamily;
  country: string;
  tenantId: string;
  callbackUrl: string | null;
  processingMode: PublicApiProcessingMode;
  createdAt: string;
  updatedAt: string;
  lastWebhookDelivery: PublicWebhookDelivery | null;
  latestDecision: DocumentDecision;
  globalConfidence: number | null;
  reviewRequired: boolean;
  processedAt: string | null;
};

export type PublicBatchStatusSnapshot = {
  batchId: string;
  externalId: string | null;
  tenantId: string;
  source: PublicBatchSource;
  status: PublicBatchStatus;
  createdAt: string;
  updatedAt: string;
  callbackUrl: string | null;
  itemCount: number;
  queued: number;
  processing: number;
  completed: number;
  review: number;
  rejected: number;
  failed: number;
  lastWebhookDelivery: PublicWebhookDelivery | null;
};

export function derivePublicSubmissionStatus(document: DocumentRecord | null): PublicSubmissionStatus {
  if (!document) return "failed";
  if (document.processedAt && (document.decision !== "pending" || document.globalConfidence !== null)) {
    if (document.status === "review" || document.reviewRequired || document.decision === "human_review") return "review";
    if (document.status === "rejected" || document.decision === "reject") return "rejected";
    return "completed";
  }
  if (document.latestJob?.status === "failed") return "failed";
  if (document.latestJob?.status === "queued") return "queued";
  if (document.latestJob?.status === "running" || document.status === "processing") return "processing";
  if (document.status === "review" || document.reviewRequired || document.decision === "human_review") return "review";
  if (document.status === "rejected" || document.decision === "reject") return "rejected";
  return "completed";
}
