import { getAllDocuments, updateDocument } from '@/lib/document-store'
import { ensureRouteAccessJson } from '@/lib/route-auth'
import { applyRetentionPolicy, getRetentionConfig } from '@/lib/retention'

export async function POST(request: Request) {
  const unauthorized = await ensureRouteAccessJson()
  if (unauthorized) return unauthorized

  const { searchParams } = new URL(request.url)
  const apply = searchParams.get('apply') === '1'
  const documents = await getAllDocuments()
  const candidates = documents
    .map((document) => ({ original: document, ...applyRetentionPolicy(document) }))
    .filter((entry) => entry.changed)

  if (apply) {
    for (const entry of candidates) {
      await updateDocument(entry.original.id, () => entry.document)
    }
  }

  return Response.json({
    apply,
    retention: getRetentionConfig(),
    candidates: candidates.map((entry) => ({
      documentId: entry.original.id,
      filename: entry.original.filename,
      updatedAt: entry.original.updatedAt
    })),
    affected: candidates.length
  })
}
