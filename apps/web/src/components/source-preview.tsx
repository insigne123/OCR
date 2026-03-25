"use client";

import type { DocumentPageRecord, ExtractedField } from "@ocr/shared";
import { useMemo, useState } from "react";
import styles from "./source-preview.module.css";

type SourcePreviewProps = {
  documentId: string;
  filename: string;
  mimeType: string;
  documentPages?: DocumentPageRecord[];
  extractedFields?: ExtractedField[];
  compact?: boolean;
};

function getSourceHint(mimeType: string) {
  if (mimeType === "application/pdf") {
    return "Vista previa embebida del PDF original para revisar la fuente antes de corregir campos.";
  }

  if (mimeType.startsWith("image/")) {
    return "Vista previa de la imagen original para comparar texto, layout y legibilidad.";
  }

  return "El archivo se entrega inline para inspeccion operativa desde la app.";
}

function hasBoundingBoxes(fields: ExtractedField[] | undefined) {
  return Boolean(fields?.some((field) => field.bbox));
}

export function SourcePreview({ documentId, filename, mimeType, documentPages = [], extractedFields = [], compact = false }: SourcePreviewProps) {
  const [imageMetrics, setImageMetrics] = useState<{ naturalWidth: number; naturalHeight: number; renderedWidth: number; renderedHeight: number } | null>(null);
  const [selectedPageNumber, setSelectedPageNumber] = useState<number>(documentPages[0]?.pageNumber ?? 1);
  const imageSrc = `/api/documents/${documentId}/source`;
  const selectedPage = useMemo(
    () => documentPages.find((page) => page.pageNumber === selectedPageNumber) ?? documentPages[0] ?? null,
    [documentPages, selectedPageNumber]
  );
  const derivedPageSrc = selectedPage ? `/api/documents/${documentId}/pages/${selectedPage.pageNumber}/source` : null;
  const overlayFields = useMemo(
    () => extractedFields.filter((field) => field.bbox && (!selectedPage || field.pageNumber === selectedPage.pageNumber)),
    [extractedFields, selectedPage]
  );
  const canOverlayImage = mimeType.startsWith("image/") && hasBoundingBoxes(extractedFields);
  const canOverlayDerivedPage = mimeType === "application/pdf" && Boolean(selectedPage?.imagePath) && hasBoundingBoxes(overlayFields);
  const previewSrc = canOverlayDerivedPage && derivedPageSrc ? derivedPageSrc : imageSrc;
  const previewTitle = canOverlayDerivedPage ? `Pagina ${selectedPage?.pageNumber} de ${filename}` : `Preview de ${filename}`;

  return (
    <section className={compact ? `${styles.panel} ${styles.compact}` : styles.panel}>
      <div className={styles.header}>
        <div>
          <span className={styles.eyebrow}>Source document</span>
          <h2 className={styles.title}>Original preview</h2>
        </div>
        <span className={styles.meta}>{mimeType}</span>
      </div>

      <p className={styles.description}>{getSourceHint(mimeType)}</p>

      {mimeType === "application/pdf" && documentPages.length > 0 ? (
        <div className={styles.pageSelector}>
          {documentPages.map((page) => (
            <button
              className={page.pageNumber === selectedPage?.pageNumber ? `${styles.pagePill} ${styles.pagePillActive}` : styles.pagePill}
              key={page.id}
              onClick={() => setSelectedPageNumber(page.pageNumber)}
              type="button"
            >
              Page {page.pageNumber}
            </button>
          ))}
        </div>
      ) : null}

      {selectedPage ? (
        <div className={styles.overlayMeta}>
          <span>quality {selectedPage.qualityScore?.toFixed(2) ?? "-"}</span>
          <span>blur {selectedPage.blurScore?.toFixed(2) ?? "-"}</span>
          <span>glare {selectedPage.glareScore?.toFixed(2) ?? "-"}</span>
          <span>coverage {selectedPage.documentCoverage?.toFixed(2) ?? "-"}</span>
          <span>profile {selectedPage.selectedOcrProfile ?? "original"}</span>
          <span>{selectedPage.captureConditions.join(", ") || "clean"}</span>
        </div>
      ) : null}

      {canOverlayImage || canOverlayDerivedPage ? (
        <>
          <div className={styles.overlayMeta}>
            <span>{overlayFields.length} bounding box(es) detectadas</span>
            <span>{canOverlayDerivedPage ? "Overlay disponible sobre pagina derivada" : "Overlay disponible para imagenes"}</span>
          </div>
          <div className={styles.imageStage}>
            <img
              alt={previewTitle}
              className={styles.previewImage}
              onLoad={(event) => {
                setImageMetrics({
                  naturalWidth: event.currentTarget.naturalWidth,
                  naturalHeight: event.currentTarget.naturalHeight,
                  renderedWidth: event.currentTarget.clientWidth,
                  renderedHeight: event.currentTarget.clientHeight
                });
              }}
              src={previewSrc}
            />

            {imageMetrics
              ? overlayFields.map((field) => {
                  const bbox = field.bbox;
                  if (!bbox) return null;

                  const scaleX = imageMetrics.renderedWidth / imageMetrics.naturalWidth;
                  const scaleY = imageMetrics.renderedHeight / imageMetrics.naturalHeight;

                  return (
                    <div
                      className={styles.overlayBox}
                      key={field.id}
                      style={{
                        left: `${bbox.x * scaleX}px`,
                        top: `${bbox.y * scaleY}px`,
                        width: `${Math.max(bbox.width * scaleX, 18)}px`,
                        height: `${Math.max(bbox.height * scaleY, 18)}px`
                      }}
                      title={`${field.label}: ${field.evidenceSpan?.text ?? field.normalizedValue ?? "sin evidencia"}`}
                    >
                      <span className={styles.overlayLabel}>{field.label}</span>
                    </div>
                  );
                })
              : null}
          </div>
        </>
      ) : (
        <iframe className={compact ? `${styles.frame} ${styles.frameCompact}` : styles.frame} src={imageSrc} title={`Preview de ${filename}`} />
      )}

      {!mimeType.startsWith("image/") && hasBoundingBoxes(extractedFields) ? (
        <p className={styles.note}>
          {canOverlayDerivedPage
            ? "El overlay se apoya en paginas derivadas persistidas para PDF."
            : "Se detectaron cajas OCR, pero el overlay visual interactivo requiere paginas derivadas persistidas o una imagen original."}
        </p>
      ) : null}
    </section>
  );
}
