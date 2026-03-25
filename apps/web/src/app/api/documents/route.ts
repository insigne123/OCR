import { AUTO_COUNTRY_CODE, type DocumentFamily } from "@ocr/shared";
import { createDocumentFromUpload, getAllDocuments } from "@/lib/document-store";
import { ensureRouteAccessJson } from "@/lib/route-auth";

export async function GET() {
  const unauthorized = await ensureRouteAccessJson();
  if (unauthorized) return unauthorized;

  const documents = await getAllDocuments();
  return Response.json({ documents });
}

export async function POST(request: Request) {
  const unauthorized = await ensureRouteAccessJson();
  if (unauthorized) return unauthorized;

  const formData = await request.formData();
  const file = formData.get("file");
  const documentFamily = (formData.get("documentFamily") as DocumentFamily | null) ?? "unclassified";
  const country = (formData.get("country") as string | null) ?? AUTO_COUNTRY_CODE;

  if (!(file instanceof File)) {
    return Response.json({ error: "Debes adjuntar un archivo valido." }, { status: 400 });
  }

  const document = await createDocumentFromUpload({
    file,
    documentFamily,
    country
  });

  return Response.json({ document }, { status: 201 });
}
