import { buildCanonicalDocumentPayload } from "@/lib/document-export";
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

  const { searchParams } = new URL(_request.url);
  const redacted = searchParams.get("redacted") === "1";

  return new Response(JSON.stringify(buildCanonicalDocumentPayload(document, { redacted }), null, 2), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "content-disposition": `attachment; filename="${document.id}.json"`
    }
  });
}
