import type { DocumentRecord } from "@ocr/shared";

import type { PublicFeedbackRecord, PublicSubmissionRecord, UsageLedgerRecord } from "@/lib/public-api-types";

type DateRange = {
  from?: string | null;
  to?: string | null;
};

function inRange(timestamp: string, range?: DateRange) {
  const value = new Date(timestamp).getTime();
  if (Number.isNaN(value)) return false;
  if (range?.from && value < new Date(range.from).getTime()) return false;
  if (range?.to && value > new Date(range.to).getTime()) return false;
  return true;
}

export function filterUsageLedger(records: UsageLedgerRecord[], range?: DateRange) {
  return records.filter((record) => inRange(record.createdAt, range));
}

export function buildUsageAnalytics(records: UsageLedgerRecord[]) {
  const terminal = records.filter((record) => record.eventType === "submission.terminal");
  const byDay = new Map<string, number>();
  const byFamily = new Map<string, number>();

  for (const record of terminal) {
    const day = record.createdAt.slice(0, 10);
    byDay.set(day, (byDay.get(day) ?? 0) + record.units);
    byFamily.set(record.documentFamily ?? "unclassified", (byFamily.get(record.documentFamily ?? "unclassified") ?? 0) + record.units);
  }

  return {
    totals: {
      terminalDocuments: terminal.reduce((acc, record) => acc + record.units, 0),
      ingestedBytes: records.reduce((acc, record) => acc + record.bytes, 0),
      submissionsTracked: new Set(terminal.map((record) => record.submissionId).filter(Boolean)).size,
    },
    byDay: [...byDay.entries()].map(([day, documents]) => ({ day, documents })),
    byFamily: [...byFamily.entries()].map(([family, documents]) => ({ family, documents })).sort((left, right) => right.documents - left.documents),
  };
}

export function buildLatencyAnalytics(records: UsageLedgerRecord[]) {
  const latencies = records
    .filter((record) => record.eventType === "submission.terminal")
    .map((record) => record.latencyMs)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value))
    .sort((left, right) => left - right);

  const percentile = (ratio: number) => {
    if (latencies.length === 0) return null;
    const index = Math.min(latencies.length - 1, Math.floor((latencies.length - 1) * ratio));
    return latencies[index];
  };

  return {
    samples: latencies.length,
    p50: percentile(0.5),
    p90: percentile(0.9),
    p99: percentile(0.99),
    averageMs: latencies.length ? Math.round(latencies.reduce((acc, value) => acc + value, 0) / latencies.length) : null,
  };
}

export function buildDecisionAnalytics(records: UsageLedgerRecord[]) {
  const terminal = records.filter((record) => record.eventType === "submission.terminal");
  const distribution = {
    auto_accept: terminal.filter((record) => record.decision === "auto_accept").length,
    accept_with_warning: terminal.filter((record) => record.decision === "accept_with_warning").length,
    human_review: terminal.filter((record) => record.decision === "human_review").length,
    reject: terminal.filter((record) => record.decision === "reject").length,
  };

  return {
    total: terminal.length,
    distribution,
    rates: {
      autoAcceptRate: terminal.length ? distribution.auto_accept / terminal.length : 0,
      reviewRate: terminal.length ? distribution.human_review / terminal.length : 0,
      rejectRate: terminal.length ? distribution.reject / terminal.length : 0,
    },
  };
}

export function buildAccuracyAnalytics(input: {
  submissions: PublicSubmissionRecord[];
  documents: DocumentRecord[];
  feedback: PublicFeedbackRecord[];
}) {
  const documentsById = new Map(input.documents.map((document) => [document.id, document]));
  const feedbackBySubmission = new Map<string, PublicFeedbackRecord[]>();

  for (const item of input.feedback) {
    const bucket = feedbackBySubmission.get(item.submissionId) ?? [];
    bucket.push(item);
    feedbackBySubmission.set(item.submissionId, bucket);
  }

  const families = new Map<string, { documents: number; correctedDocuments: number; correctedFields: number; totalFields: number }>();
  for (const submission of input.submissions) {
    const document = documentsById.get(submission.documentId);
    if (!document) continue;
    const familyKey = document.documentFamily;
    const bucket = families.get(familyKey) ?? { documents: 0, correctedDocuments: 0, correctedFields: 0, totalFields: 0 };
    const feedbackItems = feedbackBySubmission.get(submission.id) ?? [];
    const correctedFields = feedbackItems.reduce((acc, item) => acc + item.corrections.length, 0);
    const editedFields = new Set(document.reviewSessions.flatMap((session) => session.edits.map((edit) => edit.fieldName))).size;
    const totalCorrections = correctedFields + editedFields;
    bucket.documents += 1;
    bucket.totalFields += Math.max(1, document.extractedFields.length);
    bucket.correctedFields += totalCorrections;
    if (totalCorrections > 0) {
      bucket.correctedDocuments += 1;
    }
    families.set(familyKey, bucket);
  }

  return {
    families: [...families.entries()].map(([family, bucket]) => ({
      family,
      documents: bucket.documents,
      correctedDocuments: bucket.correctedDocuments,
      correctedFields: bucket.correctedFields,
      totalFields: bucket.totalFields,
      estimatedAccuracy: bucket.totalFields ? Number((1 - bucket.correctedFields / bucket.totalFields).toFixed(4)) : 1,
      correctionRate: bucket.documents ? Number((bucket.correctedDocuments / bucket.documents).toFixed(4)) : 0,
    })),
  };
}
