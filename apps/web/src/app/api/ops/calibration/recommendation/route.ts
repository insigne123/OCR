import { getAllDocuments } from '@/lib/document-store'
import { recordOpsAuditEvent } from '@/lib/ops-audit'
import { buildDecisionPolicyRecommendation } from '@/lib/ops-insights'
import { ensureRouteAccessJson } from '@/lib/route-auth'
import { buildCalibrationInsights } from '@/lib/training-dataset'

export async function GET(request: Request) {
  const unauthorized = await ensureRouteAccessJson()
  if (unauthorized) return unauthorized

  const { searchParams } = new URL(request.url)
  const persist = searchParams.get('persist') === '1'
  const documents = await getAllDocuments()
  const calibrationInsights = buildCalibrationInsights(documents)
  const recommendation = buildDecisionPolicyRecommendation(calibrationInsights)

  let persistedSnapshotId: string | null = null
  if (persist) {
    const audit = await recordOpsAuditEvent({
      action: 'snapshot.decision_policy_recommendation',
      payload: {
        recommendation,
      },
    })
    persistedSnapshotId = audit.id
  }

  return Response.json({
    persistedSnapshotId,
    recommendation,
    calibrationInsights,
  })
}
