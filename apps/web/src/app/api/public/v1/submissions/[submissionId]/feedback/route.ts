import { completeReview, getDocumentById, recordReviewEdit } from "@/lib/document-store";
import { ensurePublicApiClient } from "@/lib/public-api-auth";
import { notifyPublicSubmissionProcessed } from "@/lib/public-api-status";
import { createPublicFeedback, getPublicSubmissionById, listPublicFeedback, recordUsageLedgerEvent } from "@/lib/public-api-store";

type RouteContext = {
  params: Promise<{ submissionId: string }>;
};

type FeedbackPayload = {
  reviewer_name?: string;
  notes?: string;
  decision?: "auto_accept" | "accept_with_warning" | "human_review" | "reject";
  corrections?: Array<{
    field_id?: string;
    field_name?: string;
    new_value: string | null;
    reason?: string;
  }>;
};

export async function POST(request: Request, { params }: RouteContext) {
  const client = ensurePublicApiClient(request);
  if (client instanceof Response) return client;

  const { submissionId } = await params;
  const submission = await getPublicSubmissionById(submissionId);
  if (!submission || submission.apiClientId !== client.id) {
    return Response.json({ error: "Submission not found." }, { status: 404 });
  }

  const document = await getDocumentById(submission.documentId);
  if (!document) {
    return Response.json({ error: "Document not found." }, { status: 404 });
  }

  const payload = (await request.json()) as FeedbackPayload;
  const reviewerName = payload.reviewer_name?.trim() || client.name || "Client reviewer";
  const appliedCorrections: Array<{ fieldName: string; previousValue: string | null; newValue: string | null; reason: string }> = [];

  for (const correction of payload.corrections ?? []) {
    const targetField = correction.field_id
      ? document.extractedFields.find((field) => field.id === correction.field_id)
      : document.extractedFields.find((field) => field.fieldName === correction.field_name || field.label === correction.field_name);
    if (!targetField) {
      continue;
    }
    const updated = await recordReviewEdit({
      documentId: document.id,
      fieldId: targetField.id,
      newValue: correction.new_value ?? "",
      reason: correction.reason?.trim() || "Client feedback",
      reviewerName,
    });
    if (updated) {
      appliedCorrections.push({
        fieldName: targetField.fieldName,
        previousValue: targetField.normalizedValue,
        newValue: correction.new_value,
        reason: correction.reason?.trim() || "Client feedback",
      });
    }
  }

  const reviewed = await completeReview({
    documentId: document.id,
    reviewerName,
    notes: payload.notes,
    decision: payload.decision,
  });

  const feedback = await createPublicFeedback({
    submissionId: submission.id,
    documentId: submission.documentId,
    apiClientId: client.id,
    tenantId: submission.tenantId,
    reviewerName,
    notes: payload.notes ?? null,
    decision: payload.decision ?? null,
    corrections: appliedCorrections,
  });

  await recordUsageLedgerEvent({
    dedupeKey: `submission-feedback:${submission.id}:${feedback.id}`,
    apiClientId: client.id,
    tenantId: submission.tenantId,
    submissionId: submission.id,
    batchId: submission.batchId,
    documentId: submission.documentId,
    eventType: "submission.feedback",
    documentFamily: document.documentFamily,
    country: document.country,
    decision: payload.decision ?? reviewed?.decision ?? null,
    status: null,
    units: 1,
    bytes: 0,
    latencyMs: null,
    metadata: {
      corrections: appliedCorrections.length,
      reviewerName,
    },
  });

  if (reviewed) {
    await notifyPublicSubmissionProcessed(reviewed);
  }

  return Response.json({ feedback, document: reviewed });
}

export async function GET(request: Request, { params }: RouteContext) {
  const client = ensurePublicApiClient(request);
  if (client instanceof Response) return client;

  const { submissionId } = await params;
  const submission = await getPublicSubmissionById(submissionId);
  if (!submission || submission.apiClientId !== client.id) {
    return Response.json({ error: "Submission not found." }, { status: 404 });
  }

  const feedback = await listPublicFeedback({ apiClientId: client.id, submissionId, limit: 100 });
  return Response.json({ items: feedback });
}
