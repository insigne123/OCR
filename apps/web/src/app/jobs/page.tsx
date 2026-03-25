import { AppShell } from "@/components/app-shell";
import { JobsControl } from "@/components/jobs-control";
import { requireAuthenticatedAppUser } from "@/lib/auth";
import { getJobFeed } from "@/lib/document-store";
import { formatDate } from "@/lib/format";
import styles from "./page.module.css";

const statusLabels: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed"
};

function getStatusTone(status: string) {
  if (status === "completed") return `${styles.badge} ${styles.badgeOk}`;
  if (status === "running") return `${styles.badge} ${styles.badgeLive}`;
  if (status === "failed") return `${styles.badge} ${styles.badgeBlocked}`;
  return `${styles.badge} ${styles.badgeNeutral}`;
}

export default async function JobsPage() {
  await requireAuthenticatedAppUser();
  const jobFeed = await getJobFeed();
  const running = jobFeed.filter((entry) => entry.job?.status === "running").length;
  const failed = jobFeed.filter((entry) => entry.job?.status === "failed").length;
  const queued = jobFeed.filter((entry) => entry.job?.status === "queued").length;
  const dlq = jobFeed.filter((entry) => entry.job?.queueName === "dlq").length;

  return (
    <AppShell
      activeSection="jobs"
      eyebrow="Processing monitor"
      title="Jobs"
      subtitle="Vista inicial de monitoreo de procesamiento para seguir el estado de los documentos y preparar la futura orquestacion asincrona."
      toolbar={
        <>
          <span className={styles.toolbarChip}>Running {running}</span>
          <span className={styles.toolbarChip}>Queued {queued}</span>
          <span className={styles.toolbarChip}>Failed {failed}</span>
          <span className={styles.toolbarChip}>DLQ {dlq}</span>
          <JobsControl />
        </>
      }
    >
      <section className={styles.panel}>
        <div className={styles.panelHeader}>
          <div>
            <span className={styles.eyebrow}>Queue state</span>
            <h2 className={styles.title}>Latest job per document</h2>
          </div>
        </div>

        {jobFeed.length === 0 ? (
          <div className={styles.emptyState}>Todavia no hay jobs registrados.</div>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Status</th>
                  <th>Queue</th>
                  <th>Engine</th>
                  <th>Routing</th>
                  <th>Attempt</th>
                  <th>Stage</th>
                  <th>Created</th>
                  <th>Retry at</th>
                  <th>Finished</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {jobFeed.map(({ document, job }) => (
                  <tr key={job?.id ?? document.id}>
                    <td data-label="Document">
                      <div className={styles.documentCell}>
                        <strong>{document.filename}</strong>
                        <span>{document.documentFamily} · {document.country}</span>
                      </div>
                     </td>
                      <td data-label="Status">
                        <span className={getStatusTone(job?.status ?? "queued")}>{statusLabels[job?.status ?? "queued"] ?? job?.status}</span>
                      </td>
                      <td data-label="Queue">{job?.queueName ?? "default"}</td>
                      <td data-label="Engine">{job?.engine ?? "-"}</td>
                      <td data-label="Routing">{document.processingMetadata.routingStrategy ?? "-"}</td>
                      <td data-label="Attempt">{job ? `${job.attemptCount}/${job.maxAttempts}` : "-"}</td>
                     <td data-label="Stage">{job?.currentStage ?? "-"}</td>
                     <td data-label="Created">{job?.createdAt ? formatDate(job.createdAt) : "-"}</td>
                     <td data-label="Retry at">{job?.nextRetryAt ? formatDate(job.nextRetryAt) : "-"}</td>
                     <td data-label="Finished">{job?.finishedAt ? formatDate(job.finishedAt) : "-"}</td>
                     <td data-label="Error">{job?.errorMessage ?? "-"}</td>
                   </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </AppShell>
  );
}
