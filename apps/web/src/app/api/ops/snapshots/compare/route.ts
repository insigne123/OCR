import { listOpsAuditEvents } from '@/lib/ops-audit'
import { compareOperationalSnapshots } from '@/lib/ops-insights'
import { ensureRouteAccessJson } from '@/lib/route-auth'

export async function GET(request: Request) {
  const unauthorized = await ensureRouteAccessJson()
  if (unauthorized) return unauthorized

  const { searchParams } = new URL(request.url)
  const action = searchParams.get('action') ?? 'snapshot.learning_loop'
  const limit = Math.max(2, Math.min(Number(searchParams.get('limit') ?? '20'), 200))
  const records = await listOpsAuditEvents({
    actionPrefix: action,
    limit,
  })

  return Response.json({
    action,
    availableSnapshots: records.length,
    comparison: compareOperationalSnapshots(records, action),
  })
}
