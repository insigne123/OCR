import { enqueueDocumentProcessing } from "@/lib/document-processing";
import { ensureRouteAccessJson } from "@/lib/route-auth";

type RouteContext = {
  params: Promise<{ documentId: string }>;
};

export async function POST(request: Request, { params }: RouteContext) {
  const unauthorized = await ensureRouteAccessJson();
  if (unauthorized) return unauthorized;

  const { documentId } = await params;
  const { searchParams } = new URL(request.url);
  const force = searchParams.get("force") === "1";
  const document = await enqueueDocumentProcessing(documentId, { force });

  if (!document) {
    return Response.json({ error: "Documento no encontrado." }, { status: 404 });
  }

  return Response.json(
    {
      document,
      queued: true,
      message: "Documento agregado a la cola de procesamiento. Ejecuta un worker cycle desde Jobs para procesarlo o reintentar fallos elegibles."
    },
    { status: 202 }
  );
}
