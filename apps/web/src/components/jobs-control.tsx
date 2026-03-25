"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { isWebFeatureEnabled } from "@/lib/runtime-flags";
import styles from "./jobs-control.module.css";

export function JobsControl() {
  const router = useRouter();
  const [pendingMode, setPendingMode] = useState<"next" | "all" | "retry" | "worker" | "dlq" | null>(null);
  const [concurrency, setConcurrency] = useState("2");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dlqRequeueEnabled = isWebFeatureEnabled("jobsDlqRequeue");

  async function runJobs(action: "run_next" | "run_all" | "retry_failed" | "run_worker" | "requeue_dlq") {
    setPendingMode(
      action === "run_next"
        ? "next"
        : action === "run_all"
          ? "all"
          : action === "retry_failed"
            ? "retry"
            : action === "requeue_dlq"
              ? "dlq"
              : "worker"
    );
    setError(null);
    setMessage(null);

    const response = await fetch("/api/jobs", {
      method: "POST",
      headers: {
        "content-type": "application/json"
      },
      body: JSON.stringify({ action, concurrency: Number(concurrency) || 1 })
    });

    const payload = (await response.json()) as {
      count?: number;
      error?: string;
      concurrency?: number;
      summary?: {
        completed: number;
        failed: number;
        review: number;
        autoAccepted: number;
        acceptWithWarning: number;
      } | null;
    };

    if (!response.ok) {
      setPendingMode(null);
      setError(payload.error ?? "No se pudo ejecutar el runner de jobs.");
      return;
    }

    setPendingMode(null);
    setMessage(
      payload.count
        ? payload.summary
          ? `Worker completo: ${payload.count} job(s), ${payload.summary.completed} completed, ${payload.summary.failed} failed, ${payload.summary.review} review · concurrency ${payload.concurrency ?? 1}.`
          : action === "requeue_dlq"
            ? `DLQ requeue completo: ${payload.count} job(s) devueltos a cola con concurrency ${payload.concurrency ?? 1}.`
          : `Runner completo: ${payload.count} job(s) procesado(s) con concurrency ${payload.concurrency ?? 1}.`
        : "No habia jobs elegibles para ejecutar o reintentar."
    );
    router.refresh();
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.actions}>
        <label className={styles.inlineField}>
          <span>Concurrency</span>
          <input className={styles.inlineInput} max="8" min="1" onChange={(event) => setConcurrency(event.currentTarget.value)} type="number" value={concurrency} />
        </label>
      </div>
      <div className={styles.actions}>
        <button className={styles.primaryButton} disabled={pendingMode !== null} onClick={() => void runJobs("run_next")} type="button">
          {pendingMode === "next" ? "Running next..." : "Run next job"}
        </button>
        <button className={styles.secondaryButton} disabled={pendingMode !== null} onClick={() => void runJobs("run_all")} type="button">
          {pendingMode === "all" ? "Running all..." : "Run all queued"}
        </button>
        <button className={styles.secondaryButton} disabled={pendingMode !== null} onClick={() => void runJobs("retry_failed")} type="button">
          {pendingMode === "retry" ? "Retrying..." : "Retry failed"}
        </button>
        <button className={styles.secondaryButton} disabled={pendingMode !== null} onClick={() => void runJobs("run_worker")} type="button">
          {pendingMode === "worker" ? "Worker running..." : "Run worker cycle"}
        </button>
        {dlqRequeueEnabled ? (
          <button className={styles.secondaryButton} disabled={pendingMode !== null} onClick={() => void runJobs("requeue_dlq")} type="button">
            {pendingMode === "dlq" ? "Requeueing DLQ..." : "Requeue DLQ"}
          </button>
        ) : null}
      </div>

      {message ? <p className={styles.message}>{message}</p> : null}
      {error ? <p className={styles.error}>{error}</p> : null}
    </div>
  );
}
