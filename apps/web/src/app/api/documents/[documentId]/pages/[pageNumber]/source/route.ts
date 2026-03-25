import { getDocumentById, getStorageSignedUrl, readBinaryFromStorage } from "@/lib/document-store";
import { ensureRouteAccessInline } from "@/lib/route-auth";

type RouteContext = {
  params: Promise<{ documentId: string; pageNumber: string }>;
};

export async function GET(_request: Request, { params }: RouteContext) {
  const unauthorized = await ensureRouteAccessInline();
  if (unauthorized) return unauthorized;

  const { documentId, pageNumber } = await params;
  const document = await getDocumentById(documentId);

  if (!document) {
    return new Response("Documento no encontrado.", { status: 404 });
  }

  const page = document.documentPages.find((entry) => entry.pageNumber === Number(pageNumber));
  if (!page?.imagePath) {
    return new Response("Pagina derivada no encontrada.", { status: 404 });
  }

  const signedUrl = await getStorageSignedUrl(document.storageProvider, page.imagePath, 60);
  if (signedUrl) {
    return Response.redirect(signedUrl, 307);
  }

  const binary = await readBinaryFromStorage(document.storageProvider, page.imagePath);
  return new Response(binary, {
    headers: {
      "content-type": "image/png",
      "cache-control": "no-store"
    }
  });
}
