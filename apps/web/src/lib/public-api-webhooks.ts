import { createHmac } from "node:crypto";

import {
  createWebhookLog,
  getWebhookLogByDedupeKey,
  getWebhookLogById,
  listWebhookLogs,
  recordPublicBatchWebhook,
  recordPublicSubmissionWebhook,
  updateWebhookLog,
} from "@/lib/public-api-store";
import type { PublicWebhookDelivery, PublicWebhookLogRecord } from "@/lib/public-api-types";

function nowIso() {
  return new Date().toISOString();
}

function getWebhookConfig() {
  return {
    maxAttempts: Math.max(1, Number.parseInt(process.env.OCR_PUBLIC_WEBHOOK_MAX_ATTEMPTS ?? "3", 10) || 3),
    baseDelayMs: Math.max(1000, Number.parseInt(process.env.OCR_PUBLIC_WEBHOOK_BASE_DELAY_MS ?? "30000", 10) || 30000),
    secret: process.env.OCR_PUBLIC_WEBHOOK_SECRET ?? null,
  };
}

function buildNextRetryAt(attemptCount: number) {
  const { baseDelayMs } = getWebhookConfig();
  return new Date(Date.now() + baseDelayMs * Math.max(1, 2 ** Math.max(0, attemptCount - 1))).toISOString();
}

function publicWebhookHeaders(eventType: string, body: string, attemptedAt: string, logId: string, attemptNumber: number) {
  const headers: Record<string, string> = {
    "content-type": "application/json",
    "x-ocr-public-event": eventType,
    "x-ocr-public-delivered-at": attemptedAt,
    "x-ocr-public-delivery-id": logId,
    "x-ocr-public-attempt": String(attemptNumber),
  };
  const { secret } = getWebhookConfig();
  if (secret) {
    headers["x-ocr-public-signature"] = createHmac("sha256", secret).update(body).digest("hex");
  }
  return headers;
}

async function syncWebhookPointer(log: PublicWebhookLogRecord, delivery: PublicWebhookDelivery) {
  if (log.submissionId) {
    await recordPublicSubmissionWebhook(log.submissionId, delivery);
  }
  if (log.batchId) {
    await recordPublicBatchWebhook(log.batchId, delivery);
  }
}

export async function enqueuePublicWebhook(input: {
  submissionId: string | null;
  batchId: string | null;
  apiClientId: string;
  tenantId: string;
  source: "submission" | "batch" | "document";
  targetUrl: string;
  eventType: string;
  dedupeKey: string;
}) {
  const existing = await getWebhookLogByDedupeKey(input.dedupeKey);
  if (existing && existing.status !== "dead_letter") {
    return existing;
  }

  return createWebhookLog({
    submissionId: input.submissionId,
    batchId: input.batchId,
    apiClientId: input.apiClientId,
    tenantId: input.tenantId,
    source: input.source,
    targetUrl: input.targetUrl,
    eventType: input.eventType,
    maxAttempts: getWebhookConfig().maxAttempts,
    dedupeKey: input.dedupeKey,
  });
}

export async function attemptWebhookDelivery(log: PublicWebhookLogRecord, payload: Record<string, unknown>) {
  if (log.status === "delivered") {
    return log.deliveries.at(-1) ?? null;
  }
  if (log.nextRetryAt && new Date(log.nextRetryAt).getTime() > Date.now()) {
    return null;
  }

  const attemptedAt = nowIso();
  const attemptNumber = log.attemptCount + 1;
  const body = JSON.stringify(payload);
  let status: PublicWebhookDelivery["status"] = "failed";
  let responseStatus: number | null = null;
  let error: string | null = null;

  try {
    const response = await fetch(log.targetUrl, {
      method: "POST",
      headers: publicWebhookHeaders(log.eventType, body, attemptedAt, log.id, attemptNumber),
      body,
      cache: "no-store",
    });
    responseStatus = response.status;
    status = response.ok ? "delivered" : "failed";
    error = response.ok ? null : `Webhook returned ${response.status}`;
  } catch (cause) {
    error = cause instanceof Error ? cause.message : "Unexpected webhook error";
  }

  const nextRetryAt = status === "delivered" ? null : attemptNumber >= log.maxAttempts ? null : buildNextRetryAt(attemptNumber);
  const delivery: PublicWebhookDelivery = {
    id: log.id,
    attemptedAt,
    status: status === "failed" && !nextRetryAt ? "dead_letter" : status,
    responseStatus,
    error,
    eventType: log.eventType,
    attemptNumber,
    nextRetryAt,
    targetUrl: log.targetUrl,
    source: log.source,
  };

  const updated = await updateWebhookLog(log.id, (current) => ({
    ...current,
    status: delivery.status === "dead_letter" ? "dead_letter" : status === "delivered" ? "delivered" : "pending",
    attemptCount: attemptNumber,
    nextRetryAt,
    lastAttemptAt: attemptedAt,
    deliveries: [...current.deliveries, delivery],
  }));

  await syncWebhookPointer(updated ?? log, delivery);
  return delivery;
}

export async function drainPublicWebhookQueue(payloadFactory: (log: PublicWebhookLogRecord) => Promise<Record<string, unknown>>, options?: { apiClientId?: string; limit?: number }) {
  const logs = await listWebhookLogs({ apiClientId: options?.apiClientId, limit: Math.max(50, options?.limit ?? 10) * 5 });
  const dueLogs = logs
    .filter((log) => log.status === "pending" || log.status === "failed")
    .filter((log) => !log.nextRetryAt || new Date(log.nextRetryAt).getTime() <= Date.now())
    .sort((left, right) => new Date(left.createdAt).getTime() - new Date(right.createdAt).getTime())
    .slice(0, options?.limit ?? 10);

  const deliveries: PublicWebhookDelivery[] = [];
  for (const log of dueLogs) {
    const payload = await payloadFactory(log);
    const delivery = await attemptWebhookDelivery(log, payload);
    if (delivery) {
      deliveries.push(delivery);
    }
  }
  return deliveries;
}

export async function requeuePublicWebhookLog(logId: string) {
  const existing = await getWebhookLogById(logId);
  if (!existing) return null;
  return updateWebhookLog(logId, (current) => ({
    ...current,
    status: "pending",
    nextRetryAt: nowIso(),
  }));
}
