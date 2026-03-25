import { getAllDocuments } from "@/lib/document-store";
import { recordOpsAuditEvent } from "@/lib/ops-audit";
import { redactDocumentForExternalSharing } from "@/lib/pii";
import { ensureRouteAccessJson } from "@/lib/route-auth";
import { buildLearningLoopSnapshot } from "@/lib/training-dataset";

export async function GET(request: Request) {
  const unauthorized = await ensureRouteAccessJson();
  if (unauthorized) return unauthorized;

  const { searchParams } = new URL(request.url);
  const redacted = searchParams.get("redacted") === "1";
  const limit = Number.parseInt(searchParams.get("limit") ?? "25", 10);
  const persist = searchParams.get("persist") === "1";
  const documents = await getAllDocuments();
  const exportableDocuments = redacted ? documents.map((document) => redactDocumentForExternalSharing(document)) : documents;
  const snapshot = buildLearningLoopSnapshot(exportableDocuments, {
    limit: Number.isFinite(limit) ? Math.max(1, Math.min(limit, 100)) : 25,
  })

  let persistedSnapshotId: string | null = null
  if (persist) {
    const audit = await recordOpsAuditEvent({
      action: 'snapshot.learning_loop',
      payload: {
        redacted,
        snapshot,
      },
    })
    persistedSnapshotId = audit.id
  }

  return Response.json({
    persistedSnapshotId,
    snapshot,
  });
}
