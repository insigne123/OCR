import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { requireAuthenticatedAppUser } from "@/lib/auth";
import { getReportReadyDocuments } from "@/lib/document-store";
import { formatDate } from "@/lib/format";
import styles from "./page.module.css";

export default async function ReportsPage() {
  await requireAuthenticatedAppUser();
  const documents = await getReportReadyDocuments();

  return (
    <AppShell
      activeSection="reports"
      eyebrow="Reports library"
      title="Generated reports"
      subtitle="Repositorio operativo de snapshots HTML listos para inspeccion, export o integracion posterior."
      toolbar={
        <>
          <span className={styles.toolbarChip}>{documents.length} report(s) available</span>
          <Link className={styles.toolbarChip} href="/api/datasets/reviewed" rel="noreferrer" target="_blank">
            Reviewed dataset
          </Link>
          <Link className={styles.toolbarChip} href="/api/datasets/golden-set?evaluate=1" rel="noreferrer" target="_blank">
            Golden set
          </Link>
          <Link className={styles.toolbarChip} href="/api/datasets/learning-loop" rel="noreferrer" target="_blank">
            Learning loop
          </Link>
          <Link className={styles.toolbarChip} href="/api/datasets/registry" rel="noreferrer" target="_blank">
            Dataset registry
          </Link>
          <Link className={styles.toolbarChip} href="/api/benchmarks/golden-set?engines=rapidocr&decision_profile=balanced" rel="noreferrer" target="_blank">
            Benchmark
          </Link>
          <Link className={styles.toolbarChip} href="/api/benchmarks/routing?decision_profile=balanced" rel="noreferrer" target="_blank">
            Routing benchmark
          </Link>
          <Link className={styles.toolbarChip} href="/api/ops/audit?action_prefix=snapshot." rel="noreferrer" target="_blank">
            Audit trail
          </Link>
          <Link className={styles.toolbarChip} href="/api/ops/calibration/recommendation" rel="noreferrer" target="_blank">
            Policy recommendation
          </Link>
          <Link className={styles.toolbarChip} href="/api/ops/snapshots/compare?action=snapshot.learning_loop" rel="noreferrer" target="_blank">
            Snapshot compare
          </Link>
          <Link className={styles.toolbarChip} href="/api/metrics?format=json" rel="noreferrer" target="_blank">
            Metrics
          </Link>
        </>
      }
    >
      <section className={styles.panel}>
        <div className={styles.panelHeader}>
          <div>
            <span className={styles.eyebrow}>Library</span>
            <h2 className={styles.title}>HTML snapshots</h2>
          </div>
        </div>

        {documents.length === 0 ? (
          <div className={styles.emptyState}>Aun no hay reportes HTML generados.</div>
        ) : (
          <div className={styles.list}>
            {documents.map((document) => (
              <article className={styles.row} key={document.id}>
                <div>
                  <strong className={styles.rowTitle}>{document.filename}</strong>
                  <p className={styles.rowMeta}>Actualizado {formatDate(document.updatedAt)} · {document.documentFamily}</p>
                </div>

                <div className={styles.actions}>
                  <Link className={styles.actionSecondary} href={`/api/documents/${document.id}/json`} rel="noreferrer" target="_blank">
                    JSON
                  </Link>
                  <Link className={styles.actionSecondary} href={`/api/documents/${document.id}/csv`} rel="noreferrer" target="_blank">
                    CSV
                  </Link>
                  <Link className={styles.actionPrimary} href={`/api/documents/${document.id}/report`} rel="noreferrer" target="_blank">
                    Open HTML
                  </Link>
                  <Link className={styles.actionSecondary} href={`/documents/${document.id}`}>
                    Workspace
                  </Link>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </AppShell>
  );
}
