import { getAllDocuments } from '@/lib/document-store'
import { buildOcrCostInsights } from '@/lib/ocr-cost-insights'
import { recordOpsAuditEvent } from '@/lib/ops-audit'
import { ensureRouteAccessJson } from '@/lib/route-auth'

export async function GET(request: Request) {
  const unauthorized = await ensureRouteAccessJson()
  if (unauthorized) return unauthorized

  const { searchParams } = new URL(request.url)
  const persist = searchParams.get('persist') === '1'
  const documents = await getAllDocuments()
  const payload = buildOcrCostInsights(documents)

  let persistedSnapshotId: string | null = null
  if (persist) {
    const audit = await recordOpsAuditEvent({
      action: 'snapshot.ocr_costs',
      payload,
    })
    persistedSnapshotId = audit.id
  }

  return Response.json({
    ...payload,
    persistedSnapshotId,
  })
}
