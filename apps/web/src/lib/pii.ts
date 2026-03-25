import type { DocumentRecord } from '@ocr/shared'

function maskPreservingEnds(value: string, visibleStart = 2, visibleEnd = 2) {
  if (value.length <= visibleStart + visibleEnd) {
    return '*'.repeat(value.length)
  }
  return `${value.slice(0, visibleStart)}${'*'.repeat(Math.max(4, value.length - visibleStart - visibleEnd))}${value.slice(-visibleEnd)}`
}

function redactName(value: string | null) {
  if (!value) return value
  return value
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => `${part.slice(0, 1)}***`)
    .join(' ')
}

function redactIdentifier(value: string | null) {
  if (!value) return value
  return maskPreservingEnds(value.replace(/\s+/g, ''), 2, 2)
}

function isIdentifierField(fieldName: string) {
  return /rut|run|dni|cedula|cuenta|document/i.test(fieldName)
}

function isNameField(fieldName: string) {
  return /name|nombre|titular|holder|issuer|emisor/i.test(fieldName)
}

export function redactDocumentForExternalSharing(document: ReturnType<typeof structuredClone<DocumentRecord>> | DocumentRecord) {
  const clone = structuredClone(document)

  clone.holderName = redactName(clone.holderName)
  clone.issuer = redactName(clone.issuer)
  clone.extractedFields = clone.extractedFields.map((field) => ({
    ...field,
    normalizedValue: isIdentifierField(field.fieldName)
      ? redactIdentifier(field.normalizedValue)
      : isNameField(field.fieldName)
        ? redactName(field.normalizedValue)
        : field.normalizedValue,
    rawText: isIdentifierField(field.fieldName)
      ? redactIdentifier(field.rawText)
      : isNameField(field.fieldName)
        ? redactName(field.rawText)
        : field.rawText,
    evidenceSpan: field.evidenceSpan
      ? {
          ...field.evidenceSpan,
          text: isIdentifierField(field.fieldName)
            ? redactIdentifier(field.evidenceSpan.text) ?? field.evidenceSpan.text
            : isNameField(field.fieldName)
              ? redactName(field.evidenceSpan.text) ?? field.evidenceSpan.text
              : field.evidenceSpan.text
        }
      : null,
    candidates: field.candidates.map((candidate) => ({
      ...candidate,
      value: isIdentifierField(field.fieldName)
        ? redactIdentifier(candidate.value)
        : isNameField(field.fieldName)
          ? redactName(candidate.value)
          : candidate.value,
      rawText: isIdentifierField(field.fieldName)
        ? redactIdentifier(candidate.rawText)
        : isNameField(field.fieldName)
          ? redactName(candidate.rawText)
          : candidate.rawText,
      evidenceText: isIdentifierField(field.fieldName)
        ? redactIdentifier(candidate.evidenceText)
        : isNameField(field.fieldName)
          ? redactName(candidate.evidenceText)
          : candidate.evidenceText,
    })),
    adjudication: field.adjudication
      ? {
          ...field.adjudication,
          selectedValue: isIdentifierField(field.fieldName)
            ? redactIdentifier(field.adjudication.selectedValue)
            : isNameField(field.fieldName)
              ? redactName(field.adjudication.selectedValue)
              : field.adjudication.selectedValue
        }
      : null
  }))
  clone.processingMetadata = {
    ...clone.processingMetadata,
    ocrRuns: clone.processingMetadata.ocrRuns.map((run) => ({
      ...run,
      text: '[REDACTED]',
      pages: run.pages.map((page) => ({ ...page, text: '[REDACTED]' })),
      tokens: [],
      keyValuePairs: []
    }))
  }
  clone.reviewSessions = clone.reviewSessions.map((session) => ({
    ...session,
    reviewerName: redactName(session.reviewerName) ?? session.reviewerName,
      edits: session.edits.map((edit) => ({
        ...edit,
        reviewerName: redactName(edit.reviewerName) ?? edit.reviewerName,
        previousValue: isIdentifierField(edit.fieldName)
          ? redactIdentifier(edit.previousValue)
          : isNameField(edit.fieldName)
            ? redactName(edit.previousValue)
            : edit.previousValue,
        newValue: isIdentifierField(edit.fieldName)
          ? redactIdentifier(edit.newValue)
          : isNameField(edit.fieldName)
            ? redactName(edit.newValue)
            : edit.newValue,
      }))
  }))

  return clone
}

export function shouldRedactExternalPayloads() {
  return process.env.OCR_WEBHOOK_REDACT_PII !== 'false'
}
