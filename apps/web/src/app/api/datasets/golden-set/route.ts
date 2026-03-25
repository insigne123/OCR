import { getAllDocuments } from "@/lib/document-store";
import { ensureRouteAccessJson } from "@/lib/route-auth";
import { buildGoldenSetJson, evaluateGoldenSet } from "@/lib/training-dataset";
import { redactDocumentForExternalSharing } from "@/lib/pii";

export async function GET(request: Request) {
  const unauthorized = await ensureRouteAccessJson();
  if (unauthorized) return unauthorized;

  const { searchParams } = new URL(request.url);
  const includeEvaluation = searchParams.get("evaluate") === "1";
  const redacted = searchParams.get("redacted") === "1";
  const documents = await getAllDocuments();
  const exportableDocuments = redacted ? documents.map((document) => redactDocumentForExternalSharing(document)) : documents;
  const goldenSet = buildGoldenSetJson(exportableDocuments);

  return Response.json({
    goldenSet,
    evaluation: includeEvaluation ? evaluateGoldenSet(exportableDocuments, goldenSet) : null
  });
}
