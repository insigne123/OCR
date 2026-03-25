import { getDocumentById } from "@/lib/document-store";
import { ensureRouteAccessInline } from "@/lib/route-auth";

type RouteContext = {
  params: Promise<{ documentId: string }>;
};

export async function GET(_request: Request, { params }: RouteContext) {
  const unauthorized = await ensureRouteAccessInline();
  if (unauthorized) return unauthorized;

  const { documentId } = await params;
  const document = await getDocumentById(documentId);

  if (!document || !document.reportHtml) {
    return new Response("Reporte no disponible.", { status: 404 });
  }

  return new Response(document.reportHtml, {
    headers: {
      "content-type": "text/html; charset=utf-8"
    }
  });
}
