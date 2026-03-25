import { listOpsAuditEvents } from '@/lib/ops-audit'
import { ensureRouteAccessJson } from '@/lib/route-auth'

export async function GET(request: Request) {
  const unauthorized = await ensureRouteAccessJson()
  if (unauthorized) return unauthorized

  const { searchParams } = new URL(request.url)
  const actionPrefix = searchParams.get('action_prefix') ?? undefined
  const documentId = searchParams.get('document_id') ?? undefined
  const limit = Math.max(1, Math.min(Number(searchParams.get('limit') ?? '100'), 500))

  const records = await listOpsAuditEvents({
    actionPrefix,
    documentId,
    limit,
  })

  return Response.json({
    records,
  })
}
