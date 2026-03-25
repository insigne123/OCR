import type { DocumentRecord } from "@ocr/shared";

import { buildActiveLearningQueue, buildCalibrationInsights } from "@/lib/training-dataset";

export function buildMetricsSnapshot(documents: DocumentRecord[]) {
  const totalDocuments = documents.length;
  const now = Date.now();
  const byStatus = {
    uploaded: documents.filter((document) => document.status === "uploaded").length,
    processing: documents.filter((document) => document.status === "processing").length,
    completed: documents.filter((document) => document.status === "completed").length,
    review: documents.filter((document) => document.status === "review").length,
    rejected: documents.filter((document) => document.status === "rejected").length,
  };
  const byDecision = {
    pending: documents.filter((document) => document.decision === "pending").length,
    auto_accept: documents.filter((document) => document.decision === "auto_accept").length,
    accept_with_warning: documents.filter((document) => document.decision === "accept_with_warning").length,
    human_review: documents.filter((document) => document.decision === "human_review").length,
    reject: documents.filter((document) => document.decision === "reject").length,
  };

  const jobs = documents.flatMap((document) => (document.latestJob ? [document.latestJob] : []));
  const queuedJobs = jobs.filter((job) => job.status === "queued");
  const retryDueJobs = jobs.filter((job) => job.status === "failed" && (!job.nextRetryAt || new Date(job.nextRetryAt).getTime() <= now));
  const averageConfidence = totalDocuments
    ? documents.reduce((acc, document) => acc + (document.globalConfidence ?? 0), 0) / totalDocuments
    : 0;
  const fieldConsensuses = documents.flatMap((document) => document.extractedFields.map((field) => field.consensus).filter((value) => value != null));
  const averageAgreement = fieldConsensuses.length
    ? fieldConsensuses.reduce((acc, consensus) => acc + consensus.agreementRatio, 0) / fieldConsensuses.length
    : 0;
  const disagreementFields = fieldConsensuses.filter((consensus) => consensus.disagreement).length;
  const reviewEdits = documents.reduce((acc, document) => acc + document.reviewSessions.reduce((sessionAcc, session) => sessionAcc + session.edits.length, 0), 0);
  const datasetEligible = documents.filter((document) => document.reviewSessions.length > 0 || document.lastReviewedAt).length;
  const learningQueue = buildActiveLearningQueue(documents, { limit: 100 });
  const calibrationInsights = buildCalibrationInsights(documents);
  const packCalibrationTop = calibrationInsights.slice(0, 5).map((insight) => ({
    packId: insight.packId,
    family: insight.family,
    country: insight.country,
    reviewedDocuments: insight.reviewedDocuments,
    averageConfidence: insight.averageConfidence,
    averageAgreement: insight.averageAgreement,
    correctionRate: insight.correctionRate,
    falseAcceptCorrections: insight.falseAcceptCorrections,
    recommendation: insight.recommendation,
  }));

  return {
    totalDocuments,
    byStatus,
    byDecision,
    jobs: {
      total: jobs.length,
      queued: queuedJobs.length,
      running: jobs.filter((job) => job.status === "running").length,
      failed: jobs.filter((job) => job.status === "failed").length,
      dlq: jobs.filter((job) => job.queueName === "dlq").length,
      retryDue: retryDueJobs.length,
      oldestQueuedMinutes: queuedJobs.length
        ? Math.max(...queuedJobs.map((job) => (now - new Date(job.createdAt).getTime()) / 60000))
        : 0,
    },
    averageConfidence,
    averageAgreement,
    disagreementFields,
    reviewEdits,
    datasetEligible,
    reviewCoverage: totalDocuments ? datasetEligible / totalDocuments : 0,
    learningQueueSize: learningQueue.length,
    falseAcceptCorrections: calibrationInsights.reduce((acc, insight) => acc + insight.falseAcceptCorrections, 0),
    packsNeedingCalibration: calibrationInsights.filter((insight) => insight.recommendation !== "stable").length,
    calibrationSummary: {
      tightenAutoAccept: calibrationInsights.filter((insight) => insight.recommendation === "tighten_auto_accept").length,
      reduceReviewThreshold: calibrationInsights.filter((insight) => insight.recommendation === "reduce_review_threshold").length,
      collectMoreSamples: calibrationInsights.filter((insight) => insight.recommendation === "collect_more_samples").length,
    },
    packCalibrationTop,
  };
}

export function buildPrometheusMetrics(documents: DocumentRecord[]) {
  const snapshot = buildMetricsSnapshot(documents);
  return [
    `ocr_documents_total ${snapshot.totalDocuments}`,
    `ocr_documents_uploaded ${snapshot.byStatus.uploaded}`,
    `ocr_documents_processing ${snapshot.byStatus.processing}`,
    `ocr_documents_completed ${snapshot.byStatus.completed}`,
    `ocr_documents_review ${snapshot.byStatus.review}`,
    `ocr_documents_rejected ${snapshot.byStatus.rejected}`,
    `ocr_decision_auto_accept ${snapshot.byDecision.auto_accept}`,
    `ocr_decision_accept_with_warning ${snapshot.byDecision.accept_with_warning}`,
    `ocr_decision_human_review ${snapshot.byDecision.human_review}`,
    `ocr_decision_reject ${snapshot.byDecision.reject}`,
    `ocr_jobs_total ${snapshot.jobs.total}`,
    `ocr_jobs_failed ${snapshot.jobs.failed}`,
    `ocr_jobs_dlq ${snapshot.jobs.dlq}`,
    `ocr_jobs_retry_due ${snapshot.jobs.retryDue}`,
    `ocr_jobs_oldest_queued_minutes ${snapshot.jobs.oldestQueuedMinutes.toFixed(2)}`,
    `ocr_review_edits_total ${snapshot.reviewEdits}`,
    `ocr_dataset_eligible_documents ${snapshot.datasetEligible}`,
    `ocr_learning_queue_total ${snapshot.learningQueueSize}`,
    `ocr_false_accept_corrections_total ${snapshot.falseAcceptCorrections}`,
    `ocr_packs_needing_calibration_total ${snapshot.packsNeedingCalibration}`,
    `ocr_average_confidence ${snapshot.averageConfidence.toFixed(6)}`,
    `ocr_average_field_agreement ${snapshot.averageAgreement.toFixed(6)}`,
    `ocr_disagreement_fields_total ${snapshot.disagreementFields}`,
  ].join("\n");
}
