import { getAllDocuments } from "@/lib/document-store";
import { ensureRouteAccessInline } from "@/lib/route-auth";
import { buildReviewedDatasetExamples, buildReviewedDatasetJsonl } from "@/lib/training-dataset";
import { redactDocumentForExternalSharing } from "@/lib/pii";

export async function GET(request: Request) {
  const unauthorized = await ensureRouteAccessInline();
  if (unauthorized) return unauthorized;

  const { searchParams } = new URL(request.url);
  const format = searchParams.get("format") ?? "jsonl";
  const redacted = searchParams.get("redacted") === "1";
  const documents = await getAllDocuments();
  const exportableDocuments = redacted ? documents.map((document) => redactDocumentForExternalSharing(document)) : documents;

  if (format === "json") {
    return Response.json({ examples: buildReviewedDatasetExamples(exportableDocuments) });
  }

  return new Response(buildReviewedDatasetJsonl(exportableDocuments), {
    headers: {
      "content-type": "application/x-ndjson; charset=utf-8",
      "content-disposition": 'attachment; filename="reviewed-dataset.jsonl"'
    }
  });
}
