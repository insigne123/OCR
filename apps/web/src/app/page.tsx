import Link from "next/link";
import { documentDecisionLabels, documentStatusLabels } from "@ocr/shared";
import { AppShell } from "@/components/app-shell";
import { UploadForm } from "@/components/upload-form";
import { requireAuthenticatedAppUser } from "@/lib/auth";
import { getAllDocuments, getStorageRuntimeLabel } from "@/lib/document-store";
import { formatConfidence, formatDate } from "@/lib/format";
import styles from "./page.module.css";

type DecisionKey = keyof typeof documentDecisionLabels;
type StatusKey = keyof typeof documentStatusLabels;

function getDecisionTone(decision: DecisionKey) {
  if (decision === "auto_accept") return `${styles.badge} ${styles.badgeOk}`;
  if (decision === "accept_with_warning") return `${styles.badge} ${styles.badgeWarn}`;
  if (decision === "human_review" || decision === "pending") return `${styles.badge} ${styles.badgeReview}`;
  return `${styles.badge} ${styles.badgeBlocked}`;
}

function getStatusTone(status: StatusKey) {
  if (status === "completed") return `${styles.badge} ${styles.badgeOk}`;
  if (status === "processing") return `${styles.badge} ${styles.badgeLive}`;
  if (status === "review") return `${styles.badge} ${styles.badgeReview}`;
  if (status === "rejected") return `${styles.badge} ${styles.badgeBlocked}`;
  return `${styles.badge} ${styles.badgeNeutral}`;
}

export default async function HomePage() {
  await requireAuthenticatedAppUser();
  const documents = await getAllDocuments();

  const completed = documents.filter((document) => document.status === "completed").length;
  const processing = documents.filter((document) => document.status === "processing").length;
  const review = documents.filter((document) => document.status === "review").length;
  const reportsReady = documents.filter((document) => Boolean(document.reportHtml)).length;
  const avgConfidence = documents.length
    ? documents.reduce((total, document) => total + (document.globalConfidence ?? 0), 0) / documents.length
    : 0;

  const latestDocument = documents[0] ?? null;
  const activeReviews = documents.filter((document) => document.reviewRequired).slice(0, 4);
  const pipelineMode = process.env.OCR_API_URL ? "FastAPI engine" : "Local mock engine";
  const storageMode = getStorageRuntimeLabel();

  return (
    <AppShell
      activeSection="overview"
      eyebrow="Operations overview"
      title="Document workspace"
      subtitle="Controla la ingesta, el estado del OCR, la confianza y la salida HTML desde una interfaz de aplicacion real, sobria y enfocada en operacion."
      toolbar={
        <>
          <span className={styles.toolbarChip}>{pipelineMode}</span>
          <span className={styles.toolbarChip}>{storageMode}</span>
          {latestDocument ? (
            <Link className={styles.toolbarAction} href={`/documents/${latestDocument.id}`}>
              Open latest document
            </Link>
          ) : null}
        </>
      }
      sidebarFooter={
        <div className={styles.sidebarMetrics}>
          <div className={styles.sidebarMetric}>
            <span className={styles.sidebarLabel}>Queue</span>
            <strong className={styles.sidebarValue}>{processing + review}</strong>
          </div>
          <div className={styles.sidebarMetric}>
            <span className={styles.sidebarLabel}>Reports</span>
            <strong className={styles.sidebarValue}>{reportsReady}</strong>
          </div>
        </div>
      }
    >
      <div className={styles.layout}>
        <section className={styles.mainColumn}>
          <section className={styles.metricsGrid}>
            <article className={styles.metricCard}>
              <span className={styles.metricLabel}>Documents</span>
              <strong className={styles.metricValue}>{documents.length}</strong>
              <span className={styles.metricNote}>Activos en el workspace actual.</span>
            </article>

            <article className={styles.metricCard}>
              <span className={styles.metricLabel}>Completed</span>
              <strong className={styles.metricValue}>{completed}</strong>
              <span className={styles.metricNote}>Con salida utilizable y decision tomada.</span>
            </article>

            <article className={styles.metricCard}>
              <span className={styles.metricLabel}>Review queue</span>
              <strong className={styles.metricValue}>{review}</strong>
              <span className={styles.metricNote}>Casos que requieren confirmacion humana.</span>
            </article>

            <article className={styles.metricCard}>
              <span className={styles.metricLabel}>Average confidence</span>
              <strong className={styles.metricValue}>{formatConfidence(avgConfidence)}</strong>
              <span className={styles.metricNote}>Promedio agregado del lote cargado.</span>
            </article>
          </section>

          <section className={styles.panel} id="documents">
            <div className={styles.panelHeader}>
              <div>
                <span className={styles.panelEyebrow}>Documents</span>
                <h2 className={styles.panelTitle}>Operational queue</h2>
              </div>
              <div className={styles.panelLegend}>
                <span className={styles.legendPill}>HTML {reportsReady}</span>
                <span className={styles.legendPill}>Processing {processing}</span>
                <span className={styles.legendPill}>Review {review}</span>
              </div>
            </div>

            {documents.length === 0 ? (
              <div className={styles.emptyState}>Todavia no hay documentos cargados en el workspace.</div>
            ) : (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Document</th>
                      <th>Status</th>
                      <th>Decision</th>
                      <th>Confidence</th>
                      <th>Updated</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {documents.map((document) => (
                      <tr key={document.id}>
                        <td data-label="Document">
                          <div className={styles.documentCell}>
                            <Link className={styles.documentTitle} href={`/documents/${document.id}`}>
                              {document.filename}
                            </Link>
                            <span className={styles.documentMeta}>
                              {document.holderName ?? "Titular pendiente"} · {document.documentFamily} · {document.country}
                            </span>
                          </div>
                        </td>
                        <td data-label="Status">
                          <span className={getStatusTone(document.status)}>{documentStatusLabels[document.status]}</span>
                        </td>
                        <td data-label="Decision">
                          <span className={getDecisionTone(document.decision)}>{documentDecisionLabels[document.decision]}</span>
                        </td>
                        <td data-label="Confidence">
                          <div className={styles.statCell}>
                            <strong>{formatConfidence(document.globalConfidence)}</strong>
                            <span>{document.pageCount} page(s)</span>
                          </div>
                        </td>
                        <td data-label="Updated">
                          <div className={styles.statCell}>
                            <strong>{formatDate(document.updatedAt)}</strong>
                            <span>{document.issues.length} issue(s)</span>
                          </div>
                        </td>
                        <td data-label="Actions">
                          <div className={styles.rowActions}>
                            <Link className={styles.actionPrimary} href={`/documents/${document.id}`}>
                              Open
                            </Link>
                            {document.reviewRequired ? (
                              <Link className={styles.actionSecondary} href={`/documents/${document.id}/review`}>
                                Review
                              </Link>
                            ) : null}
                            {document.reportHtml ? (
                              <Link
                                className={styles.actionSecondary}
                                href={`/api/documents/${document.id}/report`}
                                rel="noreferrer"
                                target="_blank"
                              >
                                HTML
                              </Link>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className={styles.secondaryGrid}>
            <article className={styles.panel}>
              <div className={styles.panelHeaderCompact}>
                <div>
                  <span className={styles.panelEyebrow}>Pipeline</span>
                  <h2 className={styles.panelTitle}>Processing stages</h2>
                </div>
              </div>

              <div className={styles.stageList}>
                <div className={styles.stageRow}>
                  <span className={styles.stageIndex}>01</span>
                  <div>
                    <strong>Ingestion</strong>
                    <p>Archivo, familia documental, pais y persistencia inicial.</p>
                  </div>
                </div>
                <div className={styles.stageRow}>
                  <span className={styles.stageIndex}>02</span>
                  <div>
                    <strong>OCR / extraction</strong>
                    <p>FastAPI o fallback local preparan los campos y la lectura base.</p>
                  </div>
                </div>
                <div className={styles.stageRow}>
                  <span className={styles.stageIndex}>03</span>
                  <div>
                    <strong>Validation</strong>
                    <p>Confianza, issues y decision operativa antes del reporte final.</p>
                  </div>
                </div>
                <div className={styles.stageRow}>
                  <span className={styles.stageIndex}>04</span>
                  <div>
                    <strong>Report</strong>
                    <p>Generacion del HTML final y del resumen estructurado del documento.</p>
                  </div>
                </div>
              </div>
            </article>

            <article className={styles.panel}>
              <div className={styles.panelHeaderCompact}>
                <div>
                  <span className={styles.panelEyebrow}>Review desk</span>
                  <h2 className={styles.panelTitle}>Attention needed</h2>
                </div>
              </div>

              {activeReviews.length === 0 ? (
                <div className={styles.emptyState}>No hay documentos marcados para revision manual en este momento.</div>
              ) : (
                <div className={styles.reviewList}>
                  {activeReviews.map((document) => (
                    <Link className={styles.reviewItem} href={`/documents/${document.id}/review`} key={document.id}>
                      <div>
                        <strong>{document.filename}</strong>
                        <p>{document.issues.length} issue(s) detectados · {documentDecisionLabels[document.decision]}</p>
                      </div>
                      <span className={styles.reviewConfidence}>{formatConfidence(document.globalConfidence)}</span>
                    </Link>
                  ))}
                </div>
              )}
            </article>
          </section>
        </section>

        <aside className={styles.sideColumn}>
          <section className={styles.panel}>
            <div className={styles.panelHeaderCompact}>
              <div>
                <span className={styles.panelEyebrow}>New intake</span>
                <h2 className={styles.panelTitle}>Register document</h2>
              </div>
            </div>
            <UploadForm />
          </section>

          <section className={styles.panel}>
            <div className={styles.panelHeaderCompact}>
              <div>
                <span className={styles.panelEyebrow}>Environment</span>
                <h2 className={styles.panelTitle}>Runtime modes</h2>
              </div>
            </div>

            <dl className={styles.infoList}>
              <div className={styles.infoRow}>
                <dt>OCR engine</dt>
                <dd>{pipelineMode}</dd>
              </div>
              <div className={styles.infoRow}>
                <dt>Storage</dt>
                <dd>{storageMode}</dd>
              </div>
              <div className={styles.infoRow}>
                <dt>Output</dt>
                <dd>JSON canonico + HTML snapshot</dd>
              </div>
              <div className={styles.infoRow}>
                <dt>Current scope</dt>
                <dd>Prototype workspace ready for real OCR integration</dd>
              </div>
            </dl>
          </section>
        </aside>
      </div>
    </AppShell>
  );
}
