import { getDocumentByIdInternal } from "@/lib/document-store";
import { ensurePublicApiClient } from "@/lib/public-api-auth";
import { buildAccuracyAnalytics } from "@/lib/public-api-analytics";
import { listPublicFeedback, listPublicSubmissions } from "@/lib/public-api-store";

export async function GET(request: Request) {
  const client = ensurePublicApiClient(request);
  if (client instanceof Response) return client;

  const submissions = await listPublicSubmissions({ apiClientId: client.id, limit: 1000 });
  const feedback = await listPublicFeedback({ apiClientId: client.id, limit: 1000 });
  const documents = (
    await Promise.all(submissions.map((submission) => getDocumentByIdInternal(submission.documentId)))
  ).filter((document): document is NonNullable<typeof document> => Boolean(document));

  return Response.json(
    buildAccuracyAnalytics({
      submissions,
      documents,
      feedback,
    })
  );
}
