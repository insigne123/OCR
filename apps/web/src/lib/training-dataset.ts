import type { DocumentRecord, ExtractedField, ReviewEdit } from "@ocr/shared";

export type ReviewedDatasetExample = {
  documentId: string;
  filename: string;
  family: string;
  country: string;
  variant: string | null;
  packId: string | null;
  decision: string;
  reviewCompleted: boolean;
  source: {
    assumptions: string[];
    fields: Array<{
      fieldName: string;
      label: string;
      value: string | null;
      pageNumber: number;
      engine: string;
      evidenceText: string | null;
    }>;
  };
  target: {
    fields: Record<string, string | null>;
    edits: Array<{
      fieldName: string;
      previousValue: string | null;
      newValue: string | null;
      reason: string;
      reviewerName: string;
      createdAt: string;
    }>;
  };
  metadata: {
    processedAt: string | null;
    reviewedAt: string | null;
    processingEngine: string | null;
    classificationConfidence: number | null;
  };
};

export type GoldenSetEntry = {
  documentId: string;
  filename: string;
  family: string;
  country: string;
  variant: string | null;
  packId: string | null;
  decision: string;
  expectedFields: Record<string, string | null>;
  reviewedAt: string | null;
};

export type GoldenSetEvaluation = {
  totalDocuments: number;
  totalFields: number;
  exactMatches: number;
  exactMatchRate: number;
  perDocument: Array<{
    documentId: string;
    filename: string;
    matchedFields: number;
    totalFields: number;
    exactMatchRate: number;
    mismatches: Array<{
      fieldName: string;
      expected: string | null;
      actual: string | null;
    }>;
  }>;
};

export type GoldenSetMatchResult = {
  matchedFields: number;
  totalFields: number;
  exactMatchRate: number;
  mismatches: Array<{
    fieldName: string;
    expected: string | null;
    actual: string | null;
  }>;
};

export type ActiveLearningCandidate = {
  documentId: string;
  filename: string;
  family: string;
  country: string;
  variant: string | null;
  packId: string | null;
  decision: string;
  priorityScore: number;
  reasons: string[];
  signals: {
    correctedFields: number;
    disagreementFields: number;
    lowAgreementFields: number;
    adjudicationAbstentions: number;
    globalConfidence: number | null;
    reviewCompleted: boolean;
    falseAcceptRisk: boolean;
  };
};

export type ThresholdAdjustmentSuggestion = {
  autoAcceptConfidenceDelta: number;
  autoAcceptAgreementDelta: number;
  acceptWithWarningConfidenceDelta: number;
};

export type PackCalibrationInsight = {
  packId: string;
  family: string;
  country: string;
  variant: string | null;
  documentCount: number;
  reviewedDocuments: number;
  correctedDocuments: number;
  falseAcceptCorrections: number;
  straightThroughRate: number;
  reviewRate: number;
  correctionRate: number;
  averageConfidence: number;
  averageAgreement: number;
  disagreementRate: number;
  adjudicationAbstentionRate: number;
  recommendation: "tighten_auto_accept" | "reduce_review_threshold" | "collect_more_samples" | "stable";
  suggestedAdjustments: ThresholdAdjustmentSuggestion;
};

export type LearningLoopSnapshot = {
  generatedAt: string;
  totals: {
    reviewedDocuments: number;
    queueSize: number;
    packsTracked: number;
    falseAcceptCorrections: number;
  };
  activeLearningQueue: ActiveLearningCandidate[];
  calibrationInsights: PackCalibrationInsight[];
};

function normalizeValue(value: string | null | undefined) {
  return value == null ? null : value.trim() || null;
}

function toFieldMap(fields: ExtractedField[]) {
  return Object.fromEntries(fields.map((field) => [field.fieldName, normalizeValue(field.normalizedValue)]));
}

function latestEdits(document: DocumentRecord) {
  return document.reviewSessions
    .flatMap((session) => session.edits)
    .sort((left, right) => new Date(left.createdAt).getTime() - new Date(right.createdAt).getTime());
}

function finalFieldMap(document: DocumentRecord) {
  return toFieldMap(document.extractedFields);
}

function correctedFieldCount(document: DocumentRecord) {
  return new Set(
    latestEdits(document)
      .filter((edit) => normalizeValue(edit.previousValue) !== normalizeValue(edit.newValue))
      .map((edit) => edit.fieldName)
  ).size;
}

function agreementStats(document: DocumentRecord) {
  const consensuses = document.extractedFields.map((field) => field.consensus).filter((value) => value != null);
  const disagreementFields = consensuses.filter((consensus) => consensus.disagreement).length;
  const lowAgreementFields = consensuses.filter((consensus) => consensus.agreementRatio < 0.67).length;
  const averageAgreement = consensuses.length
    ? consensuses.reduce((acc, consensus) => acc + consensus.agreementRatio, 0) / consensuses.length
    : 0;

  return {
    total: consensuses.length,
    disagreementFields,
    lowAgreementFields,
    averageAgreement,
  };
}

function adjudicationStats(document: DocumentRecord) {
  const adjudications = document.extractedFields.map((field) => field.adjudication).filter((value) => value != null);
  const abstentions = adjudications.filter((adjudication) => adjudication.abstained).length;
  return {
    total: adjudications.length,
    abstentions,
  };
}

function resolvePackId(document: DocumentRecord) {
  return document.processingMetadata.packId ?? `${document.documentFamily}-${document.country}-${document.variant ?? "generic"}`;
}

function resolveAdjustmentSuggestion(recommendation: PackCalibrationInsight["recommendation"]): ThresholdAdjustmentSuggestion {
  if (recommendation === "tighten_auto_accept") {
    return {
      autoAcceptConfidenceDelta: 0.02,
      autoAcceptAgreementDelta: 0.05,
      acceptWithWarningConfidenceDelta: 0.01,
    };
  }

  if (recommendation === "reduce_review_threshold") {
    return {
      autoAcceptConfidenceDelta: -0.01,
      autoAcceptAgreementDelta: -0.03,
      acceptWithWarningConfidenceDelta: -0.02,
    };
  }

  return {
    autoAcceptConfidenceDelta: 0,
    autoAcceptAgreementDelta: 0,
    acceptWithWarningConfidenceDelta: 0,
  };
}

export function getReviewedDocuments(documents: DocumentRecord[]) {
  return documents.filter((document) => document.reviewSessions.length > 0 || document.lastReviewedAt);
}

export function buildReviewedDatasetExamples(documents: DocumentRecord[]): ReviewedDatasetExample[] {
  return getReviewedDocuments(documents).map((document) => ({
    documentId: document.id,
    filename: document.filename,
    family: document.documentFamily,
    country: document.country,
    variant: document.variant,
    packId: document.processingMetadata.packId,
    decision: document.decision,
    reviewCompleted: document.reviewSessions.some((session) => session.status === "completed"),
    source: {
      assumptions: document.assumptions,
      fields: document.extractedFields.map((field) => ({
        fieldName: field.fieldName,
        label: field.label,
        value: normalizeValue(field.rawText ?? field.normalizedValue),
        pageNumber: field.pageNumber,
        engine: field.engine,
        evidenceText: field.evidenceSpan?.text ?? null
      }))
    },
    target: {
      fields: finalFieldMap(document),
      edits: latestEdits(document).map((edit) => ({
        fieldName: edit.fieldName,
        previousValue: normalizeValue(edit.previousValue),
        newValue: normalizeValue(edit.newValue),
        reason: edit.reason,
        reviewerName: edit.reviewerName,
        createdAt: edit.createdAt
      }))
    },
    metadata: {
      processedAt: document.processedAt,
      reviewedAt: document.lastReviewedAt,
      processingEngine: document.processingMetadata.processingEngine,
      classificationConfidence: document.processingMetadata.classificationConfidence
    }
  }));
}

export function buildReviewedDatasetJsonl(documents: DocumentRecord[]) {
  return buildReviewedDatasetExamples(documents)
    .map((entry) => JSON.stringify(entry))
    .join("\n");
}

export function buildActiveLearningQueue(documents: DocumentRecord[], options?: { limit?: number }) {
  const queue = documents
    .map<ActiveLearningCandidate | null>((document) => {
      const correctedFields = correctedFieldCount(document);
      const agreement = agreementStats(document);
      const adjudication = adjudicationStats(document);
      const reviewCompleted = document.reviewSessions.some((session) => session.status === "completed");
      const falseAcceptRisk = document.decision === "auto_accept" && correctedFields > 0;
      const reasons: string[] = [];
      let priorityScore = 0;

      if (correctedFields > 0) {
        priorityScore += correctedFields * 18;
        reasons.push(`${correctedFields} corrected field(s)`);
      }
      if (agreement.disagreementFields > 0) {
        priorityScore += agreement.disagreementFields * 8;
        reasons.push(`${agreement.disagreementFields} OCR disagreement field(s)`);
      }
      if (agreement.lowAgreementFields > 0) {
        priorityScore += agreement.lowAgreementFields * 5;
        reasons.push(`${agreement.lowAgreementFields} low-agreement field(s)`);
      }
      if (adjudication.abstentions > 0) {
        priorityScore += adjudication.abstentions * 6;
        reasons.push(`${adjudication.abstentions} adjudication abstention(s)`);
      }
      if ((document.globalConfidence ?? 1) < 0.85) {
        priorityScore += 6;
        reasons.push("low document confidence");
      }
      if (document.decision === "human_review") {
        priorityScore += 8;
        reasons.push("human review decision");
      }
      if (falseAcceptRisk) {
        priorityScore += 20;
        reasons.push("correction after auto-accept");
      }

      if (priorityScore <= 0) {
        return null;
      }

      return {
        documentId: document.id,
        filename: document.filename,
        family: document.documentFamily,
        country: document.country,
        variant: document.variant,
        packId: document.processingMetadata.packId,
        decision: document.decision,
        priorityScore,
        reasons,
        signals: {
          correctedFields,
          disagreementFields: agreement.disagreementFields,
          lowAgreementFields: agreement.lowAgreementFields,
          adjudicationAbstentions: adjudication.abstentions,
          globalConfidence: document.globalConfidence,
          reviewCompleted,
          falseAcceptRisk,
        },
      };
    })
    .filter((candidate): candidate is ActiveLearningCandidate => candidate != null)
    .sort((left, right) => right.priorityScore - left.priorityScore);

  return queue.slice(0, options?.limit ?? 25);
}

export function buildCalibrationInsights(documents: DocumentRecord[]) {
  const buckets = new Map<string, DocumentRecord[]>();

  for (const document of documents) {
    const key = resolvePackId(document);
    const current = buckets.get(key) ?? [];
    current.push(document);
    buckets.set(key, current);
  }

  return [...buckets.entries()]
    .map<PackCalibrationInsight>(([packId, bucket]) => {
      const reviewedDocuments = bucket.filter((document) => document.reviewSessions.length > 0 || document.lastReviewedAt).length;
      const correctedDocuments = bucket.filter((document) => correctedFieldCount(document) > 0).length;
      const falseAcceptCorrections = bucket.filter((document) => document.decision === "auto_accept" && correctedFieldCount(document) > 0).length;
      const straightThroughRate = bucket.length
        ? bucket.filter((document) => document.decision === "auto_accept" || document.decision === "accept_with_warning").length / bucket.length
        : 0;
      const reviewRate = bucket.length ? bucket.filter((document) => document.decision === "human_review").length / bucket.length : 0;
      const averageConfidence = bucket.length ? bucket.reduce((acc, document) => acc + (document.globalConfidence ?? 0), 0) / bucket.length : 0;
      const agreementAggregates = bucket.map(agreementStats);
      const totalConsensusFields = agreementAggregates.reduce((acc, item) => acc + item.total, 0);
      const totalDisagreements = agreementAggregates.reduce((acc, item) => acc + item.disagreementFields, 0);
      const averageAgreement = totalConsensusFields
        ? agreementAggregates.reduce((acc, item) => acc + item.averageAgreement * item.total, 0) / totalConsensusFields
        : 0;
      const adjudicationAggregates = bucket.map(adjudicationStats);
      const totalAdjudications = adjudicationAggregates.reduce((acc, item) => acc + item.total, 0);
      const totalAbstentions = adjudicationAggregates.reduce((acc, item) => acc + item.abstentions, 0);
      const correctionRate = reviewedDocuments ? correctedDocuments / reviewedDocuments : 0;

      let recommendation: PackCalibrationInsight["recommendation"] = "stable";
      if (reviewedDocuments < 5) {
        recommendation = "collect_more_samples";
      } else if (falseAcceptCorrections > 0 || (correctionRate > 0.18 && averageAgreement < 0.88)) {
        recommendation = "tighten_auto_accept";
      } else if (reviewRate > 0.55 && correctionRate < 0.08 && averageAgreement > 0.9) {
        recommendation = "reduce_review_threshold";
      }

      return {
        packId,
        family: bucket[0]?.documentFamily ?? "unclassified",
        country: bucket[0]?.country ?? "XX",
        variant: bucket[0]?.variant ?? null,
        documentCount: bucket.length,
        reviewedDocuments,
        correctedDocuments,
        falseAcceptCorrections,
        straightThroughRate,
        reviewRate,
        correctionRate,
        averageConfidence,
        averageAgreement,
        disagreementRate: totalConsensusFields ? totalDisagreements / totalConsensusFields : 0,
        adjudicationAbstentionRate: totalAdjudications ? totalAbstentions / totalAdjudications : 0,
        recommendation,
        suggestedAdjustments: resolveAdjustmentSuggestion(recommendation),
      };
    })
    .sort((left, right) => {
      const order = {
        tighten_auto_accept: 0,
        collect_more_samples: 1,
        reduce_review_threshold: 2,
        stable: 3,
      } as const;
      if (order[left.recommendation] !== order[right.recommendation]) {
        return order[left.recommendation] - order[right.recommendation];
      }
      return right.documentCount - left.documentCount;
    });
}

export function buildLearningLoopSnapshot(documents: DocumentRecord[], options?: { limit?: number }) {
  const reviewedDocuments = getReviewedDocuments(documents);
  const activeLearningQueue = buildActiveLearningQueue(documents, { limit: options?.limit });
  const calibrationInsights = buildCalibrationInsights(documents);

  return {
    generatedAt: new Date().toISOString(),
    totals: {
      reviewedDocuments: reviewedDocuments.length,
      queueSize: activeLearningQueue.length,
      packsTracked: calibrationInsights.length,
      falseAcceptCorrections: calibrationInsights.reduce((acc, insight) => acc + insight.falseAcceptCorrections, 0),
    },
    activeLearningQueue,
    calibrationInsights,
  } satisfies LearningLoopSnapshot;
}

export function buildGoldenSet(documents: DocumentRecord[]): GoldenSetEntry[] {
  return getReviewedDocuments(documents).map((document) => ({
    documentId: document.id,
    filename: document.filename,
    family: document.documentFamily,
    country: document.country,
    variant: document.variant,
    packId: document.processingMetadata.packId,
    decision: document.decision,
    expectedFields: finalFieldMap(document),
    reviewedAt: document.lastReviewedAt
  }));
}

function lookupActualField(document: DocumentRecord, fieldName: string) {
  const direct = document.extractedFields.find((field) => field.fieldName === fieldName);
  if (direct) {
    return normalizeValue(direct.normalizedValue);
  }

  const matchingEdit = latestEdits(document)
    .filter((edit) => edit.fieldName === fieldName)
    .at(-1);
  return normalizeValue(matchingEdit?.newValue ?? null);
}

export function evaluateGoldenSet(documents: DocumentRecord[], goldenSet: GoldenSetEntry[]): GoldenSetEvaluation {
  let totalFields = 0;
  let exactMatches = 0;

  const perDocument = goldenSet.map((entry) => {
    const document = documents.find((candidate) => candidate.id === entry.documentId);
    const fieldEntries = Object.entries(entry.expectedFields);
    const mismatches: GoldenSetEvaluation["perDocument"][number]["mismatches"] = [];
    let matchedFields = 0;

    for (const [fieldName, expectedValue] of fieldEntries) {
      totalFields += 1;
      const actualValue = document ? lookupActualField(document, fieldName) : null;
      if (normalizeValue(expectedValue) === actualValue) {
        exactMatches += 1;
        matchedFields += 1;
      } else {
        mismatches.push({
          fieldName,
          expected: normalizeValue(expectedValue),
          actual: actualValue
        });
      }
    }

    return {
      documentId: entry.documentId,
      filename: entry.filename,
      matchedFields,
      totalFields: fieldEntries.length,
      exactMatchRate: fieldEntries.length ? matchedFields / fieldEntries.length : 0,
      mismatches
    };
  });

  return {
    totalDocuments: goldenSet.length,
    totalFields,
    exactMatches,
    exactMatchRate: totalFields ? exactMatches / totalFields : 0,
    perDocument
  };
}

export function evaluateDocumentAgainstGoldenEntry(document: DocumentRecord, goldenEntry: GoldenSetEntry): GoldenSetMatchResult {
  const fieldEntries = Object.entries(goldenEntry.expectedFields);
  const mismatches: GoldenSetMatchResult['mismatches'] = [];
  let matchedFields = 0;

  for (const [fieldName, expectedValue] of fieldEntries) {
    const actualValue = lookupActualField(document, fieldName);
    if (normalizeValue(expectedValue) === actualValue) {
      matchedFields += 1;
    } else {
      mismatches.push({ fieldName, expected: normalizeValue(expectedValue), actual: actualValue });
    }
  }

  return {
    matchedFields,
    totalFields: fieldEntries.length,
    exactMatchRate: fieldEntries.length ? matchedFields / fieldEntries.length : 0,
    mismatches,
  };
}

export function buildGoldenSetJson(documents: DocumentRecord[]) {
  return buildGoldenSet(documents);
}
