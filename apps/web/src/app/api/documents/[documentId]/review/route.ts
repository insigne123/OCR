import { completeReview, getDocumentById, recordReviewEdit } from "@/lib/document-store";
import { ensureRouteAccessJson } from "@/lib/route-auth";

type RouteContext = {
  params: Promise<{ documentId: string }>;
};

type ReviewPayload =
  | {
      action: "edit_field";
      fieldId: string;
      newValue: string;
      reason: string;
      reviewerName?: string;
    }
  | {
      action: "complete_review";
      notes?: string;
      reviewerName?: string;
      decision?: "auto_accept" | "accept_with_warning" | "human_review" | "reject";
    };

export async function POST(request: Request, { params }: RouteContext) {
  const unauthorized = await ensureRouteAccessJson();
  if (unauthorized) return unauthorized;

  const { documentId } = await params;
  const document = await getDocumentById(documentId);

  if (!document) {
    return Response.json({ error: "Documento no encontrado." }, { status: 404 });
  }

  const payload = (await request.json()) as ReviewPayload;
  const reviewerName = payload.reviewerName?.trim() || "Analista OCR";

  if (payload.action === "edit_field") {
    if (!payload.fieldId || !payload.reason.trim()) {
      return Response.json({ error: "Debes indicar el campo y el motivo de correccion." }, { status: 400 });
    }

    const updated = await recordReviewEdit({
      documentId,
      fieldId: payload.fieldId,
      newValue: payload.newValue,
      reason: payload.reason,
      reviewerName
    });

    return Response.json({ document: updated });
  }

  const updated = await completeReview({
    documentId,
    reviewerName,
    notes: payload.notes,
    decision: payload.decision
  });

  return Response.json({ document: updated });
}
