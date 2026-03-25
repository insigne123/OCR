import { mkdir, readFile, writeFile } from "fs/promises";
import path from "path";

import { getSupabaseServerClient, hasSupabaseServerConfig } from "@/lib/supabase/server";
import type {
  PublicBatchRecord,
  PublicFeedbackRecord,
  PublicSubmissionRecord,
  PublicWebhookDelivery,
  PublicWebhookLogRecord,
  UsageLedgerRecord,
} from "@/lib/public-api-types";

const dataDirectory = path.join(process.cwd(), ".data");
const publicApiFile = path.join(dataDirectory, "public-api.json");

type PublicApiState = {
  submissions: PublicSubmissionRecord[];
  batches: PublicBatchRecord[];
  webhookLogs: PublicWebhookLogRecord[];
  usageLedger: UsageLedgerRecord[];
  feedback: PublicFeedbackRecord[];
};

type PublicSubmissionRow = {
  id: string;
  document_id: string;
  batch_id: string | null;
  api_client_id: string;
  tenant_id: string;
  external_id: string | null;
  callback_url: string | null;
  metadata: Record<string, unknown> | null;
  filename: string;
  mime_type: string;
  size: number;
  document_family: PublicSubmissionRecord["documentFamily"];
  country: string;
  processing_mode: PublicSubmissionRecord["processingMode"];
  source: PublicSubmissionRecord["source"];
  last_webhook_delivery: PublicWebhookDelivery | null;
  created_at: string;
  updated_at: string;
};

type PublicBatchRow = {
  id: string;
  api_client_id: string;
  tenant_id: string;
  external_id: string | null;
  callback_url: string | null;
  metadata: Record<string, unknown> | null;
  source: PublicBatchRecord["source"];
  submission_ids: string[] | null;
  last_webhook_delivery: PublicWebhookDelivery | null;
  created_at: string;
  updated_at: string;
};

type PublicWebhookLogRow = {
  id: string;
  submission_id: string | null;
  batch_id: string | null;
  api_client_id: string;
  tenant_id: string;
  source: PublicWebhookLogRecord["source"];
  target_url: string;
  event_type: string;
  status: PublicWebhookLogRecord["status"];
  attempt_count: number;
  max_attempts: number;
  next_retry_at: string | null;
  created_at: string;
  updated_at: string;
  last_attempt_at: string | null;
  deliveries: PublicWebhookDelivery[] | null;
  dedupe_key: string;
};

type UsageLedgerRow = {
  id: string;
  dedupe_key: string;
  api_client_id: string;
  tenant_id: string;
  submission_id: string | null;
  batch_id: string | null;
  document_id: string | null;
  event_type: string;
  document_family: UsageLedgerRecord["documentFamily"];
  country: string | null;
  decision: UsageLedgerRecord["decision"];
  status: UsageLedgerRecord["status"];
  units: number;
  bytes: number;
  latency_ms: number | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
};

type PublicFeedbackRow = {
  id: string;
  submission_id: string;
  document_id: string;
  api_client_id: string;
  tenant_id: string;
  reviewer_name: string | null;
  notes: string | null;
  decision: PublicFeedbackRecord["decision"];
  corrections: PublicFeedbackRecord["corrections"] | null;
  created_at: string;
};

function nowIso() {
  return new Date().toISOString();
}

function useSupabaseStore() {
  return hasSupabaseServerConfig();
}

function ensureNoError(error: { message: string } | null) {
  if (error) {
    throw new Error(error.message);
  }
}

async function ensureLocalStore() {
  await mkdir(dataDirectory, { recursive: true });
  try {
    await readFile(publicApiFile, "utf-8");
  } catch {
    const initial: PublicApiState = { submissions: [], batches: [], webhookLogs: [], usageLedger: [], feedback: [] };
    await writeFile(publicApiFile, JSON.stringify(initial, null, 2), "utf-8");
  }
}

async function readLocalState(): Promise<PublicApiState> {
  await ensureLocalStore();
  const raw = await readFile(publicApiFile, "utf-8");
  const parsed = JSON.parse(raw) as Partial<PublicApiState>;
  return {
    submissions: parsed.submissions ?? [],
    batches: parsed.batches ?? [],
    webhookLogs: parsed.webhookLogs ?? [],
    usageLedger: parsed.usageLedger ?? [],
    feedback: parsed.feedback ?? [],
  };
}

async function writeLocalState(state: PublicApiState) {
  await ensureLocalStore();
  await writeFile(publicApiFile, JSON.stringify(state, null, 2), "utf-8");
}

function mapSubmissionRow(row: PublicSubmissionRow): PublicSubmissionRecord {
  return {
    id: row.id,
    documentId: row.document_id,
    batchId: row.batch_id,
    apiClientId: row.api_client_id,
    tenantId: row.tenant_id,
    externalId: row.external_id,
    callbackUrl: row.callback_url,
    metadata: row.metadata ?? {},
    filename: row.filename,
    mimeType: row.mime_type,
    size: row.size,
    documentFamily: row.document_family,
    country: row.country,
    processingMode: row.processing_mode,
    source: row.source,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    lastWebhookDelivery: row.last_webhook_delivery ?? null,
  };
}

function toSubmissionRow(record: PublicSubmissionRecord): PublicSubmissionRow {
  return {
    id: record.id,
    document_id: record.documentId,
    batch_id: record.batchId,
    api_client_id: record.apiClientId,
    tenant_id: record.tenantId,
    external_id: record.externalId,
    callback_url: record.callbackUrl,
    metadata: record.metadata,
    filename: record.filename,
    mime_type: record.mimeType,
    size: record.size,
    document_family: record.documentFamily,
    country: record.country,
    processing_mode: record.processingMode,
    source: record.source,
    last_webhook_delivery: record.lastWebhookDelivery,
    created_at: record.createdAt,
    updated_at: record.updatedAt,
  };
}

function mapBatchRow(row: PublicBatchRow): PublicBatchRecord {
  return {
    id: row.id,
    apiClientId: row.api_client_id,
    tenantId: row.tenant_id,
    externalId: row.external_id,
    callbackUrl: row.callback_url,
    metadata: row.metadata ?? {},
    source: row.source,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    submissionIds: row.submission_ids ?? [],
    lastWebhookDelivery: row.last_webhook_delivery ?? null,
  };
}

function toBatchRow(record: PublicBatchRecord): PublicBatchRow {
  return {
    id: record.id,
    api_client_id: record.apiClientId,
    tenant_id: record.tenantId,
    external_id: record.externalId,
    callback_url: record.callbackUrl,
    metadata: record.metadata,
    source: record.source,
    submission_ids: record.submissionIds,
    last_webhook_delivery: record.lastWebhookDelivery,
    created_at: record.createdAt,
    updated_at: record.updatedAt,
  };
}

function mapWebhookLogRow(row: PublicWebhookLogRow): PublicWebhookLogRecord {
  return {
    id: row.id,
    submissionId: row.submission_id,
    batchId: row.batch_id,
    apiClientId: row.api_client_id,
    tenantId: row.tenant_id,
    source: row.source,
    targetUrl: row.target_url,
    eventType: row.event_type,
    status: row.status,
    attemptCount: row.attempt_count,
    maxAttempts: row.max_attempts,
    nextRetryAt: row.next_retry_at,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    lastAttemptAt: row.last_attempt_at,
    deliveries: row.deliveries ?? [],
    dedupeKey: row.dedupe_key,
  };
}

function toWebhookLogRow(record: PublicWebhookLogRecord): PublicWebhookLogRow {
  return {
    id: record.id,
    submission_id: record.submissionId,
    batch_id: record.batchId,
    api_client_id: record.apiClientId,
    tenant_id: record.tenantId,
    source: record.source,
    target_url: record.targetUrl,
    event_type: record.eventType,
    status: record.status,
    attempt_count: record.attemptCount,
    max_attempts: record.maxAttempts,
    next_retry_at: record.nextRetryAt,
    created_at: record.createdAt,
    updated_at: record.updatedAt,
    last_attempt_at: record.lastAttemptAt,
    deliveries: record.deliveries,
    dedupe_key: record.dedupeKey,
  };
}

function mapUsageLedgerRow(row: UsageLedgerRow): UsageLedgerRecord {
  return {
    id: row.id,
    dedupeKey: row.dedupe_key,
    apiClientId: row.api_client_id,
    tenantId: row.tenant_id,
    submissionId: row.submission_id,
    batchId: row.batch_id,
    documentId: row.document_id,
    eventType: row.event_type,
    documentFamily: row.document_family,
    country: row.country,
    decision: row.decision,
    status: row.status,
    units: row.units,
    bytes: row.bytes,
    latencyMs: row.latency_ms,
    metadata: row.metadata ?? {},
    createdAt: row.created_at,
  };
}

function toUsageLedgerRow(record: UsageLedgerRecord): UsageLedgerRow {
  return {
    id: record.id,
    dedupe_key: record.dedupeKey,
    api_client_id: record.apiClientId,
    tenant_id: record.tenantId,
    submission_id: record.submissionId,
    batch_id: record.batchId,
    document_id: record.documentId,
    event_type: record.eventType,
    document_family: record.documentFamily,
    country: record.country,
    decision: record.decision,
    status: record.status,
    units: record.units,
    bytes: record.bytes,
    latency_ms: record.latencyMs,
    metadata: record.metadata,
    created_at: record.createdAt,
  };
}

function mapFeedbackRow(row: PublicFeedbackRow): PublicFeedbackRecord {
  return {
    id: row.id,
    submissionId: row.submission_id,
    documentId: row.document_id,
    apiClientId: row.api_client_id,
    tenantId: row.tenant_id,
    reviewerName: row.reviewer_name ?? "Client reviewer",
    notes: row.notes,
    decision: row.decision,
    corrections: row.corrections ?? [],
    createdAt: row.created_at,
  };
}

function toFeedbackRow(record: PublicFeedbackRecord): PublicFeedbackRow {
  return {
    id: record.id,
    submission_id: record.submissionId,
    document_id: record.documentId,
    api_client_id: record.apiClientId,
    tenant_id: record.tenantId,
    reviewer_name: record.reviewerName,
    notes: record.notes,
    decision: record.decision,
    corrections: record.corrections,
    created_at: record.createdAt,
  };
}

async function readSupabaseSubmission(id: string) {
  const response = await getSupabaseServerClient().from("public_api_submissions").select("*").eq("id", id).maybeSingle();
  ensureNoError(response.error);
  return response.data ? mapSubmissionRow(response.data as PublicSubmissionRow) : null;
}

async function readSupabaseBatch(id: string) {
  const response = await getSupabaseServerClient().from("public_api_batches").select("*").eq("id", id).maybeSingle();
  ensureNoError(response.error);
  return response.data ? mapBatchRow(response.data as PublicBatchRow) : null;
}

export async function createPublicSubmission(input: Omit<PublicSubmissionRecord, "id" | "createdAt" | "updatedAt" | "lastWebhookDelivery">) {
  const record: PublicSubmissionRecord = {
    ...input,
    id: crypto.randomUUID(),
    createdAt: nowIso(),
    updatedAt: nowIso(),
    lastWebhookDelivery: null,
  };

  if (!useSupabaseStore()) {
    const state = await readLocalState();
    state.submissions.unshift(record);
    await writeLocalState(state);
    return record;
  }

  const response = await getSupabaseServerClient().from("public_api_submissions").insert(toSubmissionRow(record)).select("*").single();
  ensureNoError(response.error);
  return mapSubmissionRow(response.data as PublicSubmissionRow);
}

export async function createPublicBatch(input: Omit<PublicBatchRecord, "id" | "createdAt" | "updatedAt" | "lastWebhookDelivery">) {
  const record: PublicBatchRecord = {
    ...input,
    id: crypto.randomUUID(),
    createdAt: nowIso(),
    updatedAt: nowIso(),
    lastWebhookDelivery: null,
  };

  if (!useSupabaseStore()) {
    const state = await readLocalState();
    state.batches.unshift(record);
    await writeLocalState(state);
    return record;
  }

  const response = await getSupabaseServerClient().from("public_api_batches").insert(toBatchRow(record)).select("*").single();
  ensureNoError(response.error);
  return mapBatchRow(response.data as PublicBatchRow);
}

export async function getPublicSubmissionById(submissionId: string) {
  if (!useSupabaseStore()) {
    const state = await readLocalState();
    return state.submissions.find((entry) => entry.id === submissionId) ?? null;
  }
  return readSupabaseSubmission(submissionId);
}

export async function listPublicSubmissions(options?: { apiClientId?: string; batchId?: string | null; limit?: number }) {
  if (!useSupabaseStore()) {
    const state = await readLocalState();
    const limit = Math.max(1, options?.limit ?? 100);
    return state.submissions
      .filter((entry) => (options?.apiClientId ? entry.apiClientId === options.apiClientId : true))
      .filter((entry) => (options?.batchId ? entry.batchId === options.batchId : true))
      .slice(0, limit);
  }

  const limit = Math.max(1, options?.limit ?? 100);
  let query = getSupabaseServerClient().from("public_api_submissions").select("*").order("created_at", { ascending: false }).limit(limit);
  if (options?.apiClientId) {
    query = query.eq("api_client_id", options.apiClientId);
  }
  if (options?.batchId) {
    query = query.eq("batch_id", options.batchId);
  }
  const response = await query;
  ensureNoError(response.error);
  return (response.data as PublicSubmissionRow[] | null)?.map(mapSubmissionRow) ?? [];
}

export async function countPublicSubmissions(options?: { apiClientId?: string; batchId?: string | null }) {
  if (!useSupabaseStore()) {
    const state = await readLocalState();
    return state.submissions
      .filter((entry) => (options?.apiClientId ? entry.apiClientId === options.apiClientId : true))
      .filter((entry) => (options?.batchId ? entry.batchId === options.batchId : true))
      .length;
  }

  let query = getSupabaseServerClient().from("public_api_submissions").select("id", { count: "exact", head: true });
  if (options?.apiClientId) {
    query = query.eq("api_client_id", options.apiClientId);
  }
  if (options?.batchId) {
    query = query.eq("batch_id", options.batchId);
  }
  const response = await query;
  ensureNoError(response.error);
  return response.count ?? 0;
}

export async function getPublicSubmissionByDocumentId(documentId: string) {
  if (!useSupabaseStore()) {
    const state = await readLocalState();
    return state.submissions.find((entry) => entry.documentId === documentId) ?? null;
  }
  const response = await getSupabaseServerClient().from("public_api_submissions").select("*").eq("document_id", documentId).maybeSingle();
  ensureNoError(response.error);
  return response.data ? mapSubmissionRow(response.data as PublicSubmissionRow) : null;
}

export async function listPublicBatchSubmissions(batchId: string) {
  if (!useSupabaseStore()) {
    const state = await readLocalState();
    return state.submissions.filter((entry) => entry.batchId === batchId);
  }
  const response = await getSupabaseServerClient().from("public_api_submissions").select("*").eq("batch_id", batchId).order("created_at", { ascending: true });
  ensureNoError(response.error);
  return (response.data as PublicSubmissionRow[] | null)?.map(mapSubmissionRow) ?? [];
}

export async function updatePublicSubmission(submissionId: string, updater: (record: PublicSubmissionRecord) => PublicSubmissionRecord) {
  if (!useSupabaseStore()) {
    const state = await readLocalState();
    const index = state.submissions.findIndex((entry) => entry.id === submissionId);
    if (index === -1) return null;
    state.submissions[index] = {
      ...updater(state.submissions[index]),
      updatedAt: nowIso(),
    };
    await writeLocalState(state);
    return state.submissions[index];
  }

  const current = await readSupabaseSubmission(submissionId);
  if (!current) return null;
  const updated: PublicSubmissionRecord = { ...updater(current), updatedAt: nowIso() };
  const response = await getSupabaseServerClient().from("public_api_submissions").update(toSubmissionRow(updated)).eq("id", submissionId).select("*").single();
  ensureNoError(response.error);
  return mapSubmissionRow(response.data as PublicSubmissionRow);
}

export async function recordPublicSubmissionWebhook(submissionId: string, delivery: PublicWebhookDelivery) {
  return updatePublicSubmission(submissionId, (record) => ({
    ...record,
    lastWebhookDelivery: delivery,
  }));
}

export async function getPublicBatchById(batchId: string) {
  if (!useSupabaseStore()) {
    const state = await readLocalState();
    return state.batches.find((entry) => entry.id === batchId) ?? null;
  }
  return readSupabaseBatch(batchId);
}

export async function listPublicBatches(options?: { apiClientId?: string; limit?: number }) {
  if (!useSupabaseStore()) {
    const state = await readLocalState();
    const limit = Math.max(1, options?.limit ?? 100);
    return state.batches.filter((entry) => (options?.apiClientId ? entry.apiClientId === options.apiClientId : true)).slice(0, limit);
  }

  const limit = Math.max(1, options?.limit ?? 100);
  let query = getSupabaseServerClient().from("public_api_batches").select("*").order("created_at", { ascending: false }).limit(limit);
  if (options?.apiClientId) {
    query = query.eq("api_client_id", options.apiClientId);
  }
  const response = await query;
  ensureNoError(response.error);
  return (response.data as PublicBatchRow[] | null)?.map(mapBatchRow) ?? [];
}

export async function updatePublicBatch(batchId: string, updater: (record: PublicBatchRecord) => PublicBatchRecord) {
  if (!useSupabaseStore()) {
    const state = await readLocalState();
    const index = state.batches.findIndex((entry) => entry.id === batchId);
    if (index === -1) return null;
    state.batches[index] = {
      ...updater(state.batches[index]),
      updatedAt: nowIso(),
    };
    await writeLocalState(state);
    return state.batches[index];
  }

  const current = await readSupabaseBatch(batchId);
  if (!current) return null;
  const updated: PublicBatchRecord = { ...updater(current), updatedAt: nowIso() };
  const response = await getSupabaseServerClient().from("public_api_batches").update(toBatchRow(updated)).eq("id", batchId).select("*").single();
  ensureNoError(response.error);
  return mapBatchRow(response.data as PublicBatchRow);
}

export async function recordPublicBatchWebhook(batchId: string, delivery: PublicWebhookDelivery) {
  return updatePublicBatch(batchId, (record) => ({
    ...record,
    lastWebhookDelivery: delivery,
  }));
}

export async function createWebhookLog(
  input: Omit<PublicWebhookLogRecord, "id" | "createdAt" | "updatedAt" | "lastAttemptAt" | "attemptCount" | "deliveries" | "status" | "nextRetryAt">
) {
  const record: PublicWebhookLogRecord = {
    ...input,
    id: crypto.randomUUID(),
    status: "pending",
    attemptCount: 0,
    nextRetryAt: nowIso(),
    createdAt: nowIso(),
    updatedAt: nowIso(),
    lastAttemptAt: null,
    deliveries: [],
  };

  if (!useSupabaseStore()) {
    const state = await readLocalState();
    state.webhookLogs.unshift(record);
    await writeLocalState(state);
    return record;
  }

  const response = await getSupabaseServerClient().from("public_api_webhook_logs").insert(toWebhookLogRow(record)).select("*").single();
  ensureNoError(response.error);
  return mapWebhookLogRow(response.data as PublicWebhookLogRow);
}

export async function listWebhookLogs(options?: {
  apiClientId?: string;
  submissionId?: string;
  batchId?: string;
  status?: PublicWebhookLogRecord["status"];
  eventType?: string;
  limit?: number;
}) {
  if (!useSupabaseStore()) {
    const state = await readLocalState();
    const limit = Math.max(1, options?.limit ?? 100);
    return state.webhookLogs
      .filter((entry) => (options?.apiClientId ? entry.apiClientId === options.apiClientId : true))
      .filter((entry) => (options?.submissionId ? entry.submissionId === options.submissionId : true))
      .filter((entry) => (options?.batchId ? entry.batchId === options.batchId : true))
      .filter((entry) => (options?.status ? entry.status === options.status : true))
      .filter((entry) => (options?.eventType ? entry.eventType === options.eventType : true))
      .slice(0, limit);
  }

  const limit = Math.max(1, options?.limit ?? 100);
  let query = getSupabaseServerClient().from("public_api_webhook_logs").select("*").order("created_at", { ascending: false }).limit(limit);
  if (options?.apiClientId) query = query.eq("api_client_id", options.apiClientId);
  if (options?.submissionId) query = query.eq("submission_id", options.submissionId);
  if (options?.batchId) query = query.eq("batch_id", options.batchId);
  if (options?.status) query = query.eq("status", options.status);
  if (options?.eventType) query = query.eq("event_type", options.eventType);
  const response = await query;
  ensureNoError(response.error);
  return (response.data as PublicWebhookLogRow[] | null)?.map(mapWebhookLogRow) ?? [];
}

export async function getWebhookLogById(logId: string) {
  if (!useSupabaseStore()) {
    const state = await readLocalState();
    return state.webhookLogs.find((entry) => entry.id === logId) ?? null;
  }
  const response = await getSupabaseServerClient().from("public_api_webhook_logs").select("*").eq("id", logId).maybeSingle();
  ensureNoError(response.error);
  return response.data ? mapWebhookLogRow(response.data as PublicWebhookLogRow) : null;
}

export async function getWebhookLogByDedupeKey(dedupeKey: string) {
  if (!useSupabaseStore()) {
    const state = await readLocalState();
    return state.webhookLogs.find((entry) => entry.dedupeKey === dedupeKey) ?? null;
  }
  const response = await getSupabaseServerClient().from("public_api_webhook_logs").select("*").eq("dedupe_key", dedupeKey).maybeSingle();
  ensureNoError(response.error);
  return response.data ? mapWebhookLogRow(response.data as PublicWebhookLogRow) : null;
}

export async function updateWebhookLog(logId: string, updater: (record: PublicWebhookLogRecord) => PublicWebhookLogRecord) {
  if (!useSupabaseStore()) {
    const state = await readLocalState();
    const index = state.webhookLogs.findIndex((entry) => entry.id === logId);
    if (index === -1) return null;
    state.webhookLogs[index] = {
      ...updater(state.webhookLogs[index]),
      updatedAt: nowIso(),
    };
    await writeLocalState(state);
    return state.webhookLogs[index];
  }

  const current = await getWebhookLogById(logId);
  if (!current) return null;
  const updated: PublicWebhookLogRecord = { ...updater(current), updatedAt: nowIso() };
  const response = await getSupabaseServerClient().from("public_api_webhook_logs").update(toWebhookLogRow(updated)).eq("id", logId).select("*").single();
  ensureNoError(response.error);
  return mapWebhookLogRow(response.data as PublicWebhookLogRow);
}

export async function recordUsageLedgerEvent(input: Omit<UsageLedgerRecord, "id" | "createdAt">) {
  if (!useSupabaseStore()) {
    const state = await readLocalState();
    const existing = state.usageLedger.find((entry) => entry.dedupeKey === input.dedupeKey);
    if (existing) {
      return existing;
    }

    const record: UsageLedgerRecord = {
      ...input,
      id: crypto.randomUUID(),
      createdAt: nowIso(),
    };
    state.usageLedger.unshift(record);
    await writeLocalState(state);
    return record;
  }

  const existing = await getSupabaseServerClient().from("public_api_usage_ledger").select("*").eq("dedupe_key", input.dedupeKey).maybeSingle();
  ensureNoError(existing.error);
  if (existing.data) {
    return mapUsageLedgerRow(existing.data as UsageLedgerRow);
  }

  const record: UsageLedgerRecord = {
    ...input,
    id: crypto.randomUUID(),
    createdAt: nowIso(),
  };
  const response = await getSupabaseServerClient().from("public_api_usage_ledger").insert(toUsageLedgerRow(record)).select("*").single();
  ensureNoError(response.error);
  return mapUsageLedgerRow(response.data as UsageLedgerRow);
}

export async function listUsageLedgerRecords(options?: {
  apiClientId?: string;
  tenantId?: string;
  submissionId?: string;
  eventType?: string;
  limit?: number;
}) {
  if (!useSupabaseStore()) {
    const state = await readLocalState();
    const limit = Math.max(1, options?.limit ?? 500);
    return state.usageLedger
      .filter((entry) => (options?.apiClientId ? entry.apiClientId === options.apiClientId : true))
      .filter((entry) => (options?.tenantId ? entry.tenantId === options.tenantId : true))
      .filter((entry) => (options?.submissionId ? entry.submissionId === options.submissionId : true))
      .filter((entry) => (options?.eventType ? entry.eventType === options.eventType : true))
      .slice(0, limit);
  }

  const limit = Math.max(1, options?.limit ?? 500);
  let query = getSupabaseServerClient().from("public_api_usage_ledger").select("*").order("created_at", { ascending: false }).limit(limit);
  if (options?.apiClientId) query = query.eq("api_client_id", options.apiClientId);
  if (options?.tenantId) query = query.eq("tenant_id", options.tenantId);
  if (options?.submissionId) query = query.eq("submission_id", options.submissionId);
  if (options?.eventType) query = query.eq("event_type", options.eventType);
  const response = await query;
  ensureNoError(response.error);
  return (response.data as UsageLedgerRow[] | null)?.map(mapUsageLedgerRow) ?? [];
}

export async function createPublicFeedback(input: Omit<PublicFeedbackRecord, "id" | "createdAt">) {
  const record: PublicFeedbackRecord = {
    ...input,
    id: crypto.randomUUID(),
    createdAt: nowIso(),
  };

  if (!useSupabaseStore()) {
    const state = await readLocalState();
    state.feedback.unshift(record);
    await writeLocalState(state);
    return record;
  }

  const response = await getSupabaseServerClient().from("public_api_feedback").insert(toFeedbackRow(record)).select("*").single();
  ensureNoError(response.error);
  return mapFeedbackRow(response.data as PublicFeedbackRow);
}

export async function listPublicFeedback(options?: { apiClientId?: string; submissionId?: string; limit?: number }) {
  if (!useSupabaseStore()) {
    const state = await readLocalState();
    const limit = Math.max(1, options?.limit ?? 100);
    return state.feedback
      .filter((entry) => (options?.apiClientId ? entry.apiClientId === options.apiClientId : true))
      .filter((entry) => (options?.submissionId ? entry.submissionId === options.submissionId : true))
      .slice(0, limit);
  }

  const limit = Math.max(1, options?.limit ?? 100);
  let query = getSupabaseServerClient().from("public_api_feedback").select("*").order("created_at", { ascending: false }).limit(limit);
  if (options?.apiClientId) query = query.eq("api_client_id", options.apiClientId);
  if (options?.submissionId) query = query.eq("submission_id", options.submissionId);
  const response = await query;
  ensureNoError(response.error);
  return (response.data as PublicFeedbackRow[] | null)?.map(mapFeedbackRow) ?? [];
}
