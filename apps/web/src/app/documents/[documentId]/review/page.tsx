import { documentDecisionLabels, documentStatusLabels } from "@ocr/shared";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { ReviewWorkbench } from "@/components/review-workbench";
import { SourcePreview } from "@/components/source-preview";
import { requireAuthenticatedAppUser } from "@/lib/auth";
import { getDocumentById } from "@/lib/document-store";
import { formatConfidence } from "@/lib/format";
import styles from "./page.module.css";

type PageProps = {
  params: Promise<{ documentId: string }>;
};

export default async function DocumentReviewPage({ params }: PageProps) {
  await requireAuthenticatedAppUser();
  const { documentId } = await params;
  const document = await getDocumentById(documentId);

  if (!document) {
    notFound();
  }

  return (
    <AppShell
      activeSection="review"
      eyebrow="Review console"
      title={`Review · ${document.filename}`}
      subtitle="Consola inicial de human-in-the-loop para corregir campos, registrar motivo y cerrar la revision del documento."
      toolbar={
        <>
          <span className={styles.badge}>{documentStatusLabels[document.status]}</span>
          <span className={styles.badge}>{documentDecisionLabels[document.decision]}</span>
          <Link className={styles.toolbarAction} href={`/documents/${document.id}`}>
            Open workspace
          </Link>
        </>
      }
      sidebarFooter={
        <div className={styles.sidebarCard}>
          <span className={styles.sidebarLabel}>Document confidence</span>
          <strong className={styles.sidebarValue}>{formatConfidence(document.globalConfidence)}</strong>
          <p className={styles.sidebarText}>{document.issues.length} issue(s) activos para revisar.</p>
          <p className={styles.sidebarText}>Pack {document.processingMetadata.packId ?? "pending"} · side {document.processingMetadata.documentSide ?? "pending"}</p>
        </div>
      }
    >
      <div className={styles.stack}>
        <SourcePreview compact documentId={document.id} documentPages={document.documentPages} extractedFields={document.extractedFields} filename={document.filename} mimeType={document.mimeType} />
        <ReviewWorkbench
          defaultDecision={document.decision}
          documentId={document.id}
          documentPages={document.documentPages}
          extractedFields={document.extractedFields}
          issues={document.issues}
          reviewSessions={document.reviewSessions}
        />
      </div>
    </AppShell>
  );
}
