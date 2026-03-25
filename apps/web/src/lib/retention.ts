import type { DocumentRecord } from '@ocr/shared'

function parseDays(value: string | undefined, fallback: number) {
  const parsed = Number(value ?? '')
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

export function getRetentionConfig() {
  return {
    reportDays: parseDays(process.env.OCR_RETENTION_DAYS_REPORTS, 90),
    reviewDays: parseDays(process.env.OCR_RETENTION_DAYS_REVIEWS, 180),
  }
}

function olderThan(dateValue: string | null | undefined, days: number) {
  if (!dateValue) return false
  const ageMs = Date.now() - new Date(dateValue).getTime()
  return ageMs > days * 24 * 60 * 60 * 1000
}

export function applyRetentionPolicy(document: DocumentRecord) {
  const config = getRetentionConfig()
  const next = structuredClone(document)
  let changed = false

  if (olderThan(next.updatedAt, config.reportDays)) {
    if (next.reportHtml) {
      next.reportHtml = null
      changed = true
    }
  }

  const retainedSessions = next.reviewSessions.filter((session) => !olderThan(session.updatedAt, config.reviewDays))
  if (retainedSessions.length !== next.reviewSessions.length) {
    next.reviewSessions = retainedSessions
    changed = true
  }

  return { changed, document: next }
}
