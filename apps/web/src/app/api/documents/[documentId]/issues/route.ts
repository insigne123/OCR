import { getDocumentById } from "@/lib/document-store";
import { ensureRouteAccessJson } from "@/lib/route-auth";

type RouteContext = {
  params: Promise<{ documentId: string }>;
};

export async function GET(_request: Request, { params }: RouteContext) {
  const unauthorized = await ensureRouteAccessJson();
  if (unauthorized) return unauthorized;

  const { documentId } = await params;
  const document = await getDocumentById(documentId);

  if (!document) {
    return Response.json({ error: "Documento no encontrado." }, { status: 404 });
  }

  return Response.json({
    issues: document.issues,
    extractedFields: document.extractedFields,
    reviewSessions: document.reviewSessions
  });
}
