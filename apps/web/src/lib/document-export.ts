import type { DocumentRecord } from "@ocr/shared";
import { redactDocumentForExternalSharing } from "@/lib/pii";

function escapeCsv(value: string | number | null | undefined) {
  const text = value == null ? "" : String(value);
  if (/[",\n]/.test(text)) {
    return `"${text.replaceAll('"', '""')}"`;
  }
  return text;
}

export function buildCanonicalDocumentPayload(document: DocumentRecord, options?: { redacted?: boolean }) {
  const base = options?.redacted ? redactDocumentForExternalSharing(document) : document;
  return {
    id: base.id,
    filename: base.filename,
    family: base.documentFamily,
    country: base.country,
    variant: base.variant,
    status: base.status,
    decision: base.decision,
    issuer: base.issuer,
    holderName: base.holderName,
    pageCount: base.pageCount,
    globalConfidence: base.globalConfidence,
    reviewRequired: base.reviewRequired,
    assumptions: base.assumptions,
    processing: base.processingMetadata,
    pages: base.documentPages,
    fields: base.extractedFields,
    issues: base.issues,
    reportSections: base.reportSections,
    reviewSessions: base.reviewSessions,
    latestJob: base.latestJob,
    generatedAt: new Date().toISOString()
  };
}

export function buildExtractedFieldsCsv(document: DocumentRecord, options?: { redacted?: boolean }) {
  const base = options?.redacted ? redactDocumentForExternalSharing(document) : document;
  const headers = [
    "document_id",
    "filename",
    "field_id",
    "section",
    "field_name",
    "label",
    "normalized_value",
    "raw_text",
    "confidence",
    "page_number",
    "engine",
    "validation_status",
    "review_status",
    "issue_ids",
    "evidence_text",
    "candidate_count",
    "agreement_ratio",
    "disagreement"
  ];

  const rows = base.extractedFields.map((field) => [
    base.id,
    base.filename,
    field.id,
    field.section,
    field.fieldName,
    field.label,
    field.normalizedValue,
    field.rawText,
    field.confidence,
    field.pageNumber,
    field.engine,
    field.validationStatus,
    field.reviewStatus,
    field.issueIds.join("|"),
    field.evidenceSpan?.text ?? "",
    field.candidates.length,
    field.consensus?.agreementRatio ?? "",
    field.consensus == null ? "" : String(field.consensus.disagreement)
  ]);

  return [headers, ...rows].map((row) => row.map((value) => escapeCsv(value)).join(",")).join("\n");
}

export function buildWebhookPayload(document: DocumentRecord, eventType: string, extra?: Record<string, unknown>, options?: { redacted?: boolean }) {
  return {
    eventType,
    document: buildCanonicalDocumentPayload(document, options),
    ...(extra ?? {})
  };
}
