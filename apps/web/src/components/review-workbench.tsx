"use client";

import type { DocumentDecision, DocumentPageRecord, ExtractedField, ReviewSession, ValidationIssue } from "@ocr/shared";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { isWebFeatureEnabled } from "@/lib/runtime-flags";
import styles from "./review-workbench.module.css";

type ReviewWorkbenchProps = {
  documentId: string;
  issues: ValidationIssue[];
  extractedFields: ExtractedField[];
  documentPages?: DocumentPageRecord[];
  reviewSessions: ReviewSession[];
  defaultDecision: DocumentDecision;
};

type PendingField = string | null;

function formatBoundingBox(field: ExtractedField) {
  if (!field.bbox) return null;
  return `x ${field.bbox.x.toFixed(0)} · y ${field.bbox.y.toFixed(0)} · w ${field.bbox.width.toFixed(0)} · h ${field.bbox.height.toFixed(0)}`;
}

function formatAgreement(field: ExtractedField) {
  if (!field.consensus) return null;
  return `${Math.round(field.consensus.agreementRatio * 100)}% agreement · ${field.consensus.enginesConsidered} engines`;
}

function formatFieldState(field: ExtractedField) {
  if (field.adjudication?.abstained) return "Adjudication abstained";
  if (field.consensus?.disagreement) return "OCR disagreement";
  if ((field.issueIds?.length ?? 0) > 0) return `${field.issueIds.length} linked issue(s)`;
  return "Ready to confirm";
}

export function ReviewWorkbench({ documentId, issues, extractedFields, documentPages = [], reviewSessions, defaultDecision }: ReviewWorkbenchProps) {
  const router = useRouter();
  const reviewAttentionQueueEnabled = isWebFeatureEnabled("reviewAttentionQueue");
  const [reviewerName, setReviewerName] = useState("Analista OCR");
  const [fieldValues, setFieldValues] = useState<Record<string, string>>(() => {
    return Object.fromEntries(extractedFields.map((field) => [field.id, field.normalizedValue ?? ""]));
  });
  const [fieldReasons, setFieldReasons] = useState<Record<string, string>>({});
  const [pendingFieldId, setPendingFieldId] = useState<PendingField>(null);
  const [reviewDecision, setReviewDecision] = useState<DocumentDecision>(defaultDecision === "pending" ? "accept_with_warning" : defaultDecision);
  const [reviewNotes, setReviewNotes] = useState("");
  const [pendingCompletion, setPendingCompletion] = useState(false);
  const [selectedPageNumber, setSelectedPageNumber] = useState<string>("all");
  const [showAttentionOnly, setShowAttentionOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const openSessions = useMemo(() => reviewSessions.filter((session) => session.status === "open"), [reviewSessions]);
  const pageOptions = useMemo(() => {
    const pageNumbers = new Set<number>([...documentPages.map((page) => page.pageNumber), ...extractedFields.map((field) => field.pageNumber)]);
    return [...pageNumbers].sort((left, right) => left - right);
  }, [documentPages, extractedFields]);
  const visibleFields = useMemo(
    () =>
      extractedFields.filter((field) => {
        if (selectedPageNumber !== "all" && field.pageNumber !== Number(selectedPageNumber)) return false;
        if (!showAttentionOnly) return true;
        return Boolean(field.issueIds.length || field.consensus?.disagreement || field.adjudication?.abstained);
      }),
    [extractedFields, selectedPageNumber, showAttentionOnly]
  );
  const summary = useMemo(
    () => ({
      disagreementFields: extractedFields.filter((field) => field.consensus?.disagreement).length,
      abstainedFields: extractedFields.filter((field) => field.adjudication?.abstained).length,
      pendingCorrections: extractedFields.filter((field) => field.reviewStatus !== "confirmed").length,
    }),
    [extractedFields]
  );

  function useCandidate(field: ExtractedField, candidateValue: string, candidateSource: string) {
    setFieldValues((current) => ({ ...current, [field.id]: candidateValue }));
    setFieldReasons((current) => ({
      ...current,
      [field.id]: current[field.id] || `Se selecciona candidato sugerido por ${candidateSource} para acelerar la revision.`
    }));
    setError(null);
  }

  async function saveField(field: ExtractedField) {
    const reason = fieldReasons[field.id]?.trim();

    if (!reason) {
      setError(`Debes indicar el motivo de correccion para ${field.label}.`);
      return;
    }

    setPendingFieldId(field.id);
    setError(null);

    const response = await fetch(`/api/documents/${documentId}/review`, {
      method: "POST",
      headers: {
        "content-type": "application/json"
      },
      body: JSON.stringify({
        action: "edit_field",
        fieldId: field.id,
        newValue: fieldValues[field.id] ?? "",
        reason,
        reviewerName
      })
    });

    const payload = (await response.json()) as { error?: string };

    if (!response.ok) {
      setPendingFieldId(null);
      setError(payload.error ?? "No se pudo guardar la correccion del campo.");
      return;
    }

    setPendingFieldId(null);
    setFieldReasons((current) => ({ ...current, [field.id]: "" }));
    router.refresh();
  }

  async function completeReview() {
    setPendingCompletion(true);
    setError(null);

    const response = await fetch(`/api/documents/${documentId}/review`, {
      method: "POST",
      headers: {
        "content-type": "application/json"
      },
      body: JSON.stringify({
        action: "complete_review",
        reviewerName,
        decision: reviewDecision,
        notes: reviewNotes
      })
    });

    const payload = (await response.json()) as { error?: string };

    if (!response.ok) {
      setPendingCompletion(false);
      setError(payload.error ?? "No se pudo completar la revision.");
      return;
    }

    setPendingCompletion(false);
    router.push(`/documents/${documentId}`);
    router.refresh();
  }

  return (
    <div className={styles.layout}>
      <section className={styles.panel}>
        <div className={styles.panelHeader}>
          <div>
            <span className={styles.eyebrow}>Field review</span>
            <h2 className={styles.title}>Correccion por campo</h2>
          </div>
          <div className={styles.headerMeta}>
            <span className={styles.metaPill}>{visibleFields.length}/{extractedFields.length} fields</span>
            <span className={styles.metaPill}>{issues.length} issues</span>
            <span className={styles.metaPill}>{summary.disagreementFields} disagreements</span>
            <span className={styles.metaPill}>{summary.abstainedFields} abstentions</span>
          </div>
        </div>

        <div className={styles.reviewerRow}>
          <label className={styles.field}>
            <span className={styles.label}>Reviewer</span>
            <input className={styles.input} onChange={(event) => setReviewerName(event.currentTarget.value)} value={reviewerName} />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>Page filter</span>
            <select className={styles.select} onChange={(event) => setSelectedPageNumber(event.currentTarget.value)} value={selectedPageNumber}>
              <option value="all">All pages</option>
              {pageOptions.map((pageNumber) => (
                <option key={pageNumber} value={String(pageNumber)}>
                  Page {pageNumber}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.toggleRow}>
            <input checked={showAttentionOnly} onChange={(event) => setShowAttentionOnly(event.currentTarget.checked)} type="checkbox" />
            <span>Show only fields with issues, disagreement or abstention</span>
          </label>
        </div>

        {error ? <p className={styles.error}>{error}</p> : null}

        <div className={styles.fieldList}>
          {visibleFields.length === 0 ? <div className={styles.emptyState}>No hay campos visibles con el filtro actual.</div> : null}
          {visibleFields.map((field) => (
            <article className={styles.fieldCard} key={field.id}>
              <div className={styles.fieldTop}>
                <div>
                  <strong className={styles.fieldTitle}>{field.label}</strong>
                  <p className={styles.fieldMeta}>
                    {field.section} · confidence {field.confidence?.toFixed(2) ?? "-"} · {field.reviewStatus} · {field.engine}
                  </p>
                </div>
                <span className={field.issueIds.length > 0 ? styles.issueBadge : styles.metaPill}>{formatFieldState(field)}</span>
              </div>

              <div className={styles.valueGrid}>
                <label className={styles.field}>
                  <span className={styles.label}>Raw OCR / source</span>
                  <input className={styles.inputMuted} disabled value={field.rawText ?? ""} />
                </label>

                <label className={styles.field}>
                  <span className={styles.label}>Normalized value</span>
                  <input
                    className={styles.input}
                    onChange={(event) => setFieldValues((current) => ({ ...current, [field.id]: event.currentTarget.value }))}
                    value={fieldValues[field.id] ?? ""}
                  />
                </label>
              </div>

              {field.evidenceSpan?.text || field.bbox ? (
                <div className={styles.evidenceBlock}>
                  {field.evidenceSpan?.text ? (
                    <p className={styles.evidenceText}>
                      Evidence: <strong>{field.evidenceSpan.text}</strong>
                    </p>
                  ) : null}
                  {formatBoundingBox(field) ? <p className={styles.evidenceMeta}>BBox: {formatBoundingBox(field)}</p> : null}
                </div>
              ) : null}

              {field.candidates.length > 0 ? (
                <div className={styles.candidateBlock}>
                  <div className={styles.candidateHeader}>
                    <strong>OCR candidates</strong>
                    {formatAgreement(field) ? <span className={styles.candidateMeta}>{formatAgreement(field)}</span> : null}
                  </div>
                  {field.consensus?.disagreement ? <p className={styles.candidateWarning}>Los motores no coinciden completamente en este campo.</p> : null}
                  <div className={styles.candidateList}>
                    {field.candidates.slice(0, 4).map((candidate) => (
                      <div className={styles.candidateItem} key={`${field.id}-${candidate.source}-${candidate.pageNumber}-${candidate.value ?? candidate.rawText ?? 'empty'}`}>
                        <div className={styles.candidateTop}>
                          <span className={styles.candidateEngine}>{candidate.source}</span>
                          <span className={styles.candidateMeta}>
                            {candidate.selected ? "selected" : candidate.matchType} · score {candidate.score.toFixed(2)}
                          </span>
                        </div>
                        <p className={styles.candidateValue}>{candidate.value ?? candidate.rawText ?? "Sin valor"}</p>
                        {candidate.evidenceText && candidate.evidenceText !== candidate.value ? (
                          <p className={styles.candidateEvidence}>Evidence: {candidate.evidenceText}</p>
                        ) : null}
                        {candidate.value && candidate.value !== (fieldValues[field.id] ?? "") ? (
                          <button className={styles.inlineButton} onClick={() => useCandidate(field, candidate.value ?? "", candidate.source)} type="button">
                            Use candidate
                          </button>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {field.adjudication ? (
                <div className={styles.adjudicationBlock}>
                  <div className={styles.candidateHeader}>
                    <strong>Adjudication</strong>
                    <span className={styles.candidateMeta}>{field.adjudication.method}</span>
                  </div>
                  <p className={styles.candidateValue}>
                    {field.adjudication.abstained
                      ? "Abstained"
                      : field.adjudication.selectedValue ?? field.normalizedValue ?? "Sin valor"}
                  </p>
                  <p className={styles.candidateEvidence}>{field.adjudication.rationale}</p>
                </div>
              ) : null}

              <label className={styles.field}>
                <span className={styles.label}>Correction reason</span>
                <textarea
                  className={styles.textarea}
                  onChange={(event) => setFieldReasons((current) => ({ ...current, [field.id]: event.currentTarget.value }))}
                  placeholder="Explica por que corriges este campo."
                  rows={3}
                  value={fieldReasons[field.id] ?? ""}
                />
              </label>

              <div className={styles.actions}>
                <button
                  className={styles.primaryButton}
                  disabled={pendingFieldId === field.id}
                  onClick={() => void saveField(field)}
                  type="button"
                >
                  {pendingFieldId === field.id ? "Saving..." : "Save correction"}
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <aside className={styles.sideColumn}>
        {reviewAttentionQueueEnabled ? (
          <section className={styles.panel}>
            <div className={styles.panelHeaderCompact}>
              <div>
                <span className={styles.eyebrow}>Issue focus</span>
                <h2 className={styles.title}>Attention queue</h2>
              </div>
            </div>

            <div className={styles.sessionList}>
              {issues.length === 0 ? (
                <div className={styles.emptyState}>No hay issues activos para este documento.</div>
              ) : (
                issues.slice(0, 8).map((issue) => (
                  <article className={styles.sessionCard} key={issue.id}>
                    <div className={styles.sessionTop}>
                      <strong>{issue.field}</strong>
                      <span className={styles.metaPill}>{issue.severity}</span>
                    </div>
                    <p className={styles.fieldMeta}>{issue.type}</p>
                    <p className={styles.sessionNotes}>{issue.message}</p>
                  </article>
                ))
              )}
            </div>
          </section>
        ) : null}

        <section className={styles.panel}>
          <div className={styles.panelHeaderCompact}>
            <div>
              <span className={styles.eyebrow}>Review status</span>
              <h2 className={styles.title}>Sessions</h2>
            </div>
          </div>

          <div className={styles.sessionList}>
            {reviewSessions.length === 0 ? (
              <div className={styles.emptyState}>Aun no hay sesiones de revision guardadas.</div>
            ) : (
              reviewSessions.map((session) => (
                <article className={styles.sessionCard} key={session.id}>
                  <div className={styles.sessionTop}>
                    <strong>{session.reviewerName}</strong>
                    <span className={styles.metaPill}>{session.status}</span>
                  </div>
                  <p className={styles.fieldMeta}>{session.edits.length} edit(s) · {new Date(session.updatedAt).toLocaleString("es-CL")}</p>
                  {session.notes ? <p className={styles.sessionNotes}>{session.notes}</p> : null}
                </article>
              ))
            )}
          </div>

          {openSessions.length > 0 ? <p className={styles.helperText}>Hay una sesion abierta. Las correcciones nuevas se agregaran a esa sesion.</p> : null}
        </section>

        <section className={styles.panel}>
          <div className={styles.panelHeaderCompact}>
            <div>
              <span className={styles.eyebrow}>Resolve review</span>
              <h2 className={styles.title}>Complete review</h2>
            </div>
          </div>

          <label className={styles.field}>
            <span className={styles.label}>Decision after review</span>
            <select className={styles.select} onChange={(event) => setReviewDecision(event.currentTarget.value as DocumentDecision)} value={reviewDecision}>
              <option value="auto_accept">Auto accept</option>
              <option value="accept_with_warning">Accept with warning</option>
              <option value="human_review">Keep in review</option>
              <option value="reject">Reject</option>
            </select>
          </label>

          <label className={styles.field}>
            <span className={styles.label}>Review notes</span>
            <textarea
              className={styles.textarea}
              onChange={(event) => setReviewNotes(event.currentTarget.value)}
              placeholder="Agrega un resumen de la revision realizada."
              rows={4}
              value={reviewNotes}
            />
          </label>

          <button className={styles.primaryButton} disabled={pendingCompletion} onClick={() => void completeReview()} type="button">
            {pendingCompletion ? "Closing review..." : "Complete review"}
          </button>
        </section>
      </aside>
    </div>
  );
}
