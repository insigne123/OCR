import Link from "next/link";
import { documentDecisionLabels, documentStatusLabels } from "@ocr/shared";
import { notFound } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { ProcessDocumentButton } from "@/components/process-document-button";
import { SourcePreview } from "@/components/source-preview";
import { requireAuthenticatedAppUser } from "@/lib/auth";
import { getDocumentById } from "@/lib/document-store";
import { formatConfidence, formatDate } from "@/lib/format";
import styles from "./page.module.css";

type PageProps = {
  params: Promise<{ documentId: string }>;
};

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

export default async function DocumentDetailPage({ params }: PageProps) {
  await requireAuthenticatedAppUser();
  const { documentId } = await params;
  const document = await getDocumentById(documentId);

  if (!document) {
    notFound();
  }

  const pipelineMode = process.env.OCR_API_URL ? "FastAPI engine" : "Local mock engine";

  return (
    <AppShell
      activeSection="documents"
      eyebrow="Document detail"
      title={document.filename}
      subtitle="Workspace individual para inspeccion, reproceso, lectura estructurada, validaciones y visualizacion del HTML final."
      toolbar={
        <>
          <span className={getStatusTone(document.status)}>{documentStatusLabels[document.status]}</span>
          <span className={getDecisionTone(document.decision)}>{documentDecisionLabels[document.decision]}</span>
          <Link className={styles.toolbarAction} href={`/api/documents/${document.id}/json`} rel="noreferrer" target="_blank">
            Export JSON
          </Link>
          {document.reviewRequired ? (
            <Link className={styles.toolbarAction} href={`/documents/${document.id}/review`}>
              Open review
            </Link>
          ) : null}
          <Link className={styles.toolbarAction} href="/">
            Back to overview
          </Link>
        </>
      }
      sidebarFooter={
        <div className={styles.sidebarCard}>
          <span className={styles.sidebarLabel}>Pipeline</span>
          <strong className={styles.sidebarValue}>{pipelineMode}</strong>
          <p className={styles.sidebarText}>Motor activo para este documento y su proximo reproceso.</p>
        </div>
      }
    >
      <div className={styles.layout}>
        <section className={styles.mainColumn}>
          <section className={styles.metricsGrid}>
            <article className={styles.metricCard}>
              <span className={styles.metricLabel}>Confidence</span>
              <strong className={styles.metricValue}>{formatConfidence(document.globalConfidence)}</strong>
              <span className={styles.metricNote}>Valor agregado del documento procesado.</span>
            </article>

            <article className={styles.metricCard}>
              <span className={styles.metricLabel}>Issues</span>
              <strong className={styles.metricValue}>{document.issues.length}</strong>
              <span className={styles.metricNote}>Observaciones y reglas activadas en el pipeline.</span>
            </article>

            <article className={styles.metricCard}>
              <span className={styles.metricLabel}>Sections</span>
              <strong className={styles.metricValue}>{document.reportSections.length}</strong>
              <span className={styles.metricNote}>Bloques estructurados disponibles para reporte.</span>
            </article>

            <article className={styles.metricCard}>
              <span className={styles.metricLabel}>Latest job</span>
              <strong className={styles.metricValue}>{document.latestJob?.status ?? "Pending"}</strong>
              <span className={styles.metricNote}>Estado mas reciente de la cola y el procesamiento.</span>
            </article>
          </section>

          <section className={styles.panel}>
            <div className={styles.panelHeader}>
              <div>
                <span className={styles.panelEyebrow}>Preprocess</span>
                <h2 className={styles.panelTitle}>Page quality</h2>
              </div>
            </div>

            {document.documentPages.length === 0 ? (
              <div className={styles.emptyState}>Todavia no hay metadata de paginas derivadas para este documento.</div>
            ) : (
              <div className={styles.tableWrap}>
                <table className={styles.dataTable}>
                  <thead>
                    <tr>
                      <th>Page</th>
                      <th>Resolution</th>
                      <th>Quality</th>
                      <th>Blur</th>
                      <th>Glare</th>
                      <th>Embedded text</th>
                    </tr>
                  </thead>
                  <tbody>
                    {document.documentPages.map((page) => (
                      <tr key={page.id}>
                        <td>{page.pageNumber}</td>
                        <td>{page.width && page.height ? `${page.width} x ${page.height}` : "-"}</td>
                        <td>{formatConfidence(page.qualityScore)}</td>
                        <td>{formatConfidence(page.blurScore)}</td>
                        <td>{formatConfidence(page.glareScore)}</td>
                        <td>{page.hasEmbeddedText ? "Yes" : "No"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className={styles.panel}>
            <div className={styles.panelHeader}>
              <div>
                <span className={styles.panelEyebrow}>Extraction</span>
                <h2 className={styles.panelTitle}>Structured data</h2>
              </div>
              <div className={styles.panelTags}>
                <span className={styles.tag}>{document.documentFamily}</span>
                <span className={styles.tag}>{document.country}</span>
                {document.variant ? <span className={styles.tag}>{document.variant}</span> : null}
              </div>
            </div>

            {document.reportSections.length === 0 ? (
              <div className={styles.emptyState}>Todavia no hay lectura estructurada para este documento.</div>
            ) : (
              <div className={styles.sectionStack}>
                {document.reportSections.map((section) => (
                  <section className={styles.sectionBlock} key={section.id}>
                    <h3 className={styles.sectionHeading}>{section.title}</h3>

                    {section.variant === "text" && section.body ? <p className={styles.bodyText}>{section.body}</p> : null}

                    {section.variant === "pairs" && section.rows ? (
                      <table className={styles.dataTable}>
                        <tbody>
                          {section.rows.map((row) => (
                            <tr key={`${section.id}-${row[0]}`}>
                              <th scope="row">{row[0]}</th>
                              <td>{row[1]}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : null}

                    {section.variant === "table" && section.columns && section.rows ? (
                      <div className={styles.tableWrap}>
                        <table className={styles.dataTable}>
                          <thead>
                            <tr>
                              {section.columns.map((column) => (
                                <th key={`${section.id}-${column}`}>{column}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {section.rows.map((row, rowIndex) => (
                              <tr key={`${section.id}-${rowIndex}`}>
                                {row.map((cell, cellIndex) => (
                                  <td key={`${section.id}-${rowIndex}-${cellIndex}`}>{cell}</td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : null}

                    {section.note ? <p className={styles.note}>{section.note}</p> : null}
                  </section>
                ))}
              </div>
            )}
          </section>

          <section className={styles.panel}>
            <div className={styles.panelHeader}>
              <div>
                <span className={styles.panelEyebrow}>Report</span>
                <h2 className={styles.panelTitle}>HTML snapshot</h2>
              </div>
              <div className={styles.panelTags}>
                <Link className={styles.toolbarAction} href={`/api/documents/${document.id}/csv`} rel="noreferrer" target="_blank">
                  Export CSV
                </Link>
                {document.reportHtml ? (
                  <Link className={styles.toolbarAction} href={`/api/documents/${document.id}/report`} rel="noreferrer" target="_blank">
                    Open HTML
                  </Link>
                ) : null}
              </div>
            </div>

            {document.reportHtml ? (
              <iframe className={styles.reportFrame} src={`/api/documents/${document.id}/report`} title={`Reporte HTML de ${document.filename}`} />
            ) : (
              <div className={styles.emptyState}>Aun no se genero el HTML final para este documento.</div>
            )}
          </section>

          <SourcePreview compact documentId={document.id} documentPages={document.documentPages} extractedFields={document.extractedFields} filename={document.filename} mimeType={document.mimeType} />
        </section>

        <aside className={styles.sideColumn}>
          <section className={styles.panel}>
            <div className={styles.panelHeaderCompact}>
              <div>
                <span className={styles.panelEyebrow}>Action</span>
                <h2 className={styles.panelTitle}>Process control</h2>
              </div>
            </div>
            <ProcessDocumentButton documentId={document.id} status={document.status} />
          </section>

          <section className={styles.panel}>
            <div className={styles.panelHeaderCompact}>
              <div>
                <span className={styles.panelEyebrow}>Inspector</span>
                <h2 className={styles.panelTitle}>Document summary</h2>
              </div>
            </div>

            <dl className={styles.infoList}>
              <div className={styles.infoRow}>
                <dt>Issuer</dt>
                <dd>{document.issuer ?? "Pending"}</dd>
              </div>
              <div className={styles.infoRow}>
                <dt>Holder</dt>
                <dd>{document.holderName ?? "Pending"}</dd>
              </div>
              <div className={styles.infoRow}>
                <dt>Storage path</dt>
                <dd>{document.storagePath}</dd>
              </div>
              <div className={styles.infoRow}>
                <dt>Latest job</dt>
                <dd>{document.latestJob ? `${document.latestJob.status} · ${document.latestJob.engine}` : "No job yet"}</dd>
              </div>
              <div className={styles.infoRow}>
                <dt>Pack</dt>
                <dd>{document.processingMetadata.packId ?? "Pending"}</dd>
              </div>
              <div className={styles.infoRow}>
                <dt>Side</dt>
                <dd>{document.processingMetadata.documentSide ?? "Pending"}</dd>
              </div>
              <div className={styles.infoRow}>
                <dt>Cross-side</dt>
                <dd>{document.processingMetadata.crossSideDetected ? "Detected" : "No"}</dd>
              </div>
              <div className={styles.infoRow}>
                <dt>Decision profile</dt>
                <dd>{document.processingMetadata.decisionProfile ?? "Pending"}</dd>
              </div>
              <div className={styles.infoRow}>
                <dt>Requested OCR</dt>
                <dd>{document.processingMetadata.requestedVisualEngine ?? "Default"}</dd>
              </div>
              <div className={styles.infoRow}>
                <dt>Source</dt>
                <dd>{document.processingMetadata.extractionSource ?? "Pending"}</dd>
              </div>
              <div className={styles.infoRow}>
                <dt>Classifier</dt>
                <dd>{document.processingMetadata.classificationConfidence?.toFixed(2) ?? "-"}</dd>
              </div>
              <div className={styles.infoRow}>
                <dt>Last updated</dt>
                <dd>{formatDate(document.updatedAt)}</dd>
              </div>
              <div className={styles.infoRow}>
                <dt>Review required</dt>
                <dd>{document.reviewRequired ? "Yes" : "No"}</dd>
              </div>
            </dl>

            {document.processingMetadata.processingTrace.length > 0 ? (
              <div className={styles.assumptionBox}>
                <h3 className={styles.assumptionTitle}>Processing trace</h3>
                <ul className={styles.assumptionList}>
                  {document.processingMetadata.processingTrace.map((entry) => (
                    <li key={`${entry.stage}-${entry.startedAt}`}>
                      <strong>{entry.stage}</strong> - {entry.status} - {entry.durationMs.toFixed(1)} ms - {entry.summary}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>

          <section className={styles.panel}>
            <div className={styles.panelHeaderCompact}>
              <div>
                <span className={styles.panelEyebrow}>Validation</span>
                <h2 className={styles.panelTitle}>Issues</h2>
              </div>
            </div>

            {document.issues.length === 0 ? (
              <div className={styles.emptyState}>No hay issues registrados para este documento.</div>
            ) : (
              <div className={styles.issueList}>
                {document.issues.map((issue) => (
                  <article className={styles.issueCard} key={issue.id}>
                    <div className={styles.issueHeader}>
                      <span className={styles.issueType}>{issue.type}</span>
                      <strong className={styles.issueField}>{issue.field}</strong>
                    </div>
                    <p className={styles.bodyText}>{issue.message}</p>
                    <p className={styles.note}>Suggested action: {issue.suggestedAction}</p>
                  </article>
                ))}
              </div>
            )}

            {document.assumptions.length > 0 ? (
              <div className={styles.assumptionBox}>
                <h3 className={styles.assumptionTitle}>Assumptions</h3>
                <ul className={styles.assumptionList}>
                  {document.assumptions.map((assumption) => (
                    <li key={assumption}>{assumption}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>
        </aside>
      </div>
    </AppShell>
  );
}
