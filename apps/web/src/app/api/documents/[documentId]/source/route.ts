import { getDocumentById, getDocumentSignedUrl, readDocumentBinary } from "@/lib/document-store";
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

  const signedUrl = await getDocumentSignedUrl(document, 60);
  if (signedUrl) {
    return Response.redirect(signedUrl, 307);
  }

  const fileBuffer = await readDocumentBinary(document);

  return new Response(fileBuffer, {
    headers: {
      "content-type": document.mimeType,
      "content-disposition": `inline; filename="${document.filename}"`,
      "cache-control": "no-store"
    }
  });
}
