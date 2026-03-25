import { buildExtractedFieldsCsv } from "@/lib/document-export";
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

  if (!document) {
    return new Response("Documento no encontrado.", { status: 404 });
  }

  const { searchParams } = new URL(_request.url);
  const redacted = searchParams.get("redacted") === "1";

  return new Response(buildExtractedFieldsCsv(document, { redacted }), {
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": `attachment; filename="${document.id}.csv"`
    }
  });
}
