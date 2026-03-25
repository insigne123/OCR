import Link from "next/link";
import { documentDecisionLabels, documentStatusLabels } from "@ocr/shared";
import { AppShell } from "@/components/app-shell";
import { requireAuthenticatedAppUser } from "@/lib/auth";
import { getReviewQueueDocuments } from "@/lib/document-store";
import { formatConfidence, formatDate } from "@/lib/format";
import styles from "./page.module.css";

export default async function ReviewQueuePage() {
  await requireAuthenticatedAppUser();
  const documents = await getReviewQueueDocuments();

  return (
    <AppShell
      activeSection="review"
      eyebrow="Human in the loop"
      title="Review queue"
      subtitle="Casos que requieren confirmacion humana, correcciones de campo o una decision final antes de ser liberados."
      toolbar={<span className={styles.toolbarChip}>{documents.length} document(s) in queue</span>}
    >
      <section className={styles.panel}>
        <div className={styles.panelHeader}>
          <div>
            <span className={styles.eyebrow}>Queue</span>
            <h2 className={styles.title}>Documents waiting for review</h2>
          </div>
        </div>

        {documents.length === 0 ? (
          <div className={styles.emptyState}>No hay documentos en la cola de revision.</div>
        ) : (
          <div className={styles.cardGrid}>
            {documents.map((document) => (
              <article className={styles.card} key={document.id}>
                <div className={styles.cardTop}>
                  <div>
                    <h3 className={styles.cardTitle}>{document.filename}</h3>
                    <p className={styles.cardMeta}>
                      {document.holderName ?? "Titular pendiente"} · {document.documentFamily} · {document.country}
                    </p>
                  </div>
                  <span className={styles.badge}>{documentStatusLabels[document.status]}</span>
                </div>

                <dl className={styles.infoList}>
                  <div className={styles.infoRow}>
                    <dt>Decision</dt>
                    <dd>{documentDecisionLabels[document.decision]}</dd>
                  </div>
                  <div className={styles.infoRow}>
                    <dt>Confidence</dt>
                    <dd>{formatConfidence(document.globalConfidence)}</dd>
                  </div>
                  <div className={styles.infoRow}>
                    <dt>Issues</dt>
                    <dd>{document.issues.length}</dd>
                  </div>
                  <div className={styles.infoRow}>
                    <dt>Updated</dt>
                    <dd>{formatDate(document.updatedAt)}</dd>
                  </div>
                </dl>

                <div className={styles.actions}>
                  <Link className={styles.actionPrimary} href={`/documents/${document.id}/review`}>
                    Open review console
                  </Link>
                  <Link className={styles.actionSecondary} href={`/documents/${document.id}`}>
                    Open workspace
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
