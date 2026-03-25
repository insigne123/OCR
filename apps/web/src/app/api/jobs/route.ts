import { getJobFeed } from "@/lib/document-store";
import { getDlqDocuments, getRetryableFailedDocuments, requeueDlqJobs, runQueuedJobs, runWorkerCycle } from "@/lib/document-processing";
import { ensureRouteAccessJson } from "@/lib/route-auth";

type JobRunPayload = {
  action?: "run_next" | "run_all" | "retry_failed" | "run_worker" | "requeue_dlq";
  limit?: number;
  concurrency?: number;
};

function hasInternalWorkerAccess(request: Request) {
  const configured = process.env.OCR_WORKER_API_KEY;
  if (!configured) return false;
  return request.headers.get("x-worker-key") === configured;
}

export async function GET() {
  const unauthorized = await ensureRouteAccessJson();
  if (unauthorized) return unauthorized;

  const [jobs, retryableFailed, dlqDocuments] = await Promise.all([getJobFeed(), getRetryableFailedDocuments(), getDlqDocuments()]);
  return Response.json({ jobs, retryableFailed: retryableFailed.length, dlqDocuments: dlqDocuments.length });
}

export async function POST(request: Request) {
  const unauthorized = hasInternalWorkerAccess(request) ? null : await ensureRouteAccessJson();
  if (unauthorized) return unauthorized;

  const payload = (await request.json().catch(() => ({}))) as JobRunPayload;
  const action = payload.action ?? "run_worker";
  const limit = action === "run_next" ? 1 : Math.max(1, payload.limit ?? 25);
  const concurrency = Math.max(1, Math.min(payload.concurrency ?? 2, 8));
  const workerResult =
    action === "requeue_dlq"
      ? { processed: await requeueDlqJobs(limit), summary: null }
      : action === "retry_failed"
      ? { processed: await runQueuedJobs(limit, { includeRetries: true, concurrency }), summary: null }
      : action === "run_worker"
        ? await runWorkerCycle(limit, { concurrency })
        : { processed: await runQueuedJobs(limit, { includeRetries: action === "run_all", concurrency }), summary: null };

  return Response.json({
    processed: workerResult.processed,
    count: workerResult.processed.length,
    concurrency,
    summary: workerResult.summary,
  });
}
