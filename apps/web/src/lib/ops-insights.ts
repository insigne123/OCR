import type { OpsAuditRecord } from '@/lib/ops-audit'
import type { PackCalibrationInsight } from '@/lib/training-dataset'

export type DecisionPolicyRecommendation = {
  generatedAt: string
  summary: {
    totalRules: number
    tightenedRules: number
    relaxedRules: number
    sampleCollectionRules: number
  }
  config: {
    defaults: Record<string, never>
    rules: Array<{
      family: string
      country: string
      packId: string
      thresholds: {
        autoAcceptConfidence: number
        autoAcceptAgreement: number
        acceptWithWarningConfidence: number
        reviewAgreement: number
        crossSideConfidence: number
      }
    }>
  }
}

export type SnapshotComparisonResult = {
  action: string
  latestId: string
  previousId: string
  latestCreatedAt: string
  previousCreatedAt: string
  summary: string[]
  metrics: Record<string, number | string | null>
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

export function buildDecisionPolicyRecommendation(insights: PackCalibrationInsight[]): DecisionPolicyRecommendation {
  const relevant = insights.filter((insight) => insight.recommendation !== 'stable')
  const rules = relevant.map((insight) => {
    const baseConfidence = clamp(insight.averageConfidence || 0.85, 0.75, 0.99)
    const baseAgreement = clamp(insight.averageAgreement || 0.85, 0.55, 0.99)
    const thresholds = {
      autoAcceptConfidence: clamp(baseConfidence + 0.04 + insight.suggestedAdjustments.autoAcceptConfidenceDelta, 0.82, 0.995),
      autoAcceptAgreement: clamp(baseAgreement + 0.02 + insight.suggestedAdjustments.autoAcceptAgreementDelta, 0.6, 0.99),
      acceptWithWarningConfidence: clamp(baseConfidence - 0.03 + insight.suggestedAdjustments.acceptWithWarningConfidenceDelta, 0.68, 0.98),
      reviewAgreement: clamp(baseAgreement - 0.15, 0.45, 0.92),
      crossSideConfidence: clamp(baseConfidence - 0.01, 0.78, 0.97),
    }

    return {
      family: insight.family,
      country: insight.country,
      packId: insight.packId,
      thresholds,
    }
  })

  return {
    generatedAt: new Date().toISOString(),
    summary: {
      totalRules: rules.length,
      tightenedRules: relevant.filter((insight) => insight.recommendation === 'tighten_auto_accept').length,
      relaxedRules: relevant.filter((insight) => insight.recommendation === 'reduce_review_threshold').length,
      sampleCollectionRules: relevant.filter((insight) => insight.recommendation === 'collect_more_samples').length,
    },
    config: {
      defaults: {},
      rules,
    },
  }
}

function compareLearningLoopSnapshots(latest: OpsAuditRecord, previous: OpsAuditRecord): SnapshotComparisonResult {
  const latestSnapshot = latest.payload.snapshot as {
    totals?: { queueSize?: number; falseAcceptCorrections?: number; packsTracked?: number }
    calibrationInsights?: Array<{ recommendation: string }>
  } | undefined
  const previousSnapshot = previous.payload.snapshot as {
    totals?: { queueSize?: number; falseAcceptCorrections?: number; packsTracked?: number }
    calibrationInsights?: Array<{ recommendation: string }>
  } | undefined

  const latestQueue = latestSnapshot?.totals?.queueSize ?? 0
  const previousQueue = previousSnapshot?.totals?.queueSize ?? 0
  const latestFalseAccepts = latestSnapshot?.totals?.falseAcceptCorrections ?? 0
  const previousFalseAccepts = previousSnapshot?.totals?.falseAcceptCorrections ?? 0
  const latestTightened = (latestSnapshot?.calibrationInsights ?? []).filter((item) => item.recommendation === 'tighten_auto_accept').length
  const previousTightened = (previousSnapshot?.calibrationInsights ?? []).filter((item) => item.recommendation === 'tighten_auto_accept').length

  return {
    action: latest.action,
    latestId: latest.id,
    previousId: previous.id,
    latestCreatedAt: latest.createdAt,
    previousCreatedAt: previous.createdAt,
    summary: [
      `Queue delta ${latestQueue - previousQueue}.`,
      `False accept corrections delta ${latestFalseAccepts - previousFalseAccepts}.`,
      `Packs needing tighter auto-accept delta ${latestTightened - previousTightened}.`,
    ],
    metrics: {
      queueDelta: latestQueue - previousQueue,
      falseAcceptCorrectionsDelta: latestFalseAccepts - previousFalseAccepts,
      tightenAutoAcceptDelta: latestTightened - previousTightened,
      latestQueueSize: latestQueue,
      previousQueueSize: previousQueue,
    },
  }
}

function compareRoutingSnapshots(latest: OpsAuditRecord, previous: OpsAuditRecord): SnapshotComparisonResult {
  const latestPayload = latest.payload as {
    recommendedOverall?: { strategy?: string | null }
    results?: Array<{ strategy: string; exactMatchRate: number; straightThroughRate: number; estimatedCostPerDocument: number }>
  }
  const previousPayload = previous.payload as {
    recommendedOverall?: { strategy?: string | null }
    results?: Array<{ strategy: string; exactMatchRate: number; straightThroughRate: number; estimatedCostPerDocument: number }>
  }

  const latestMap = new Map((latestPayload.results ?? []).map((result) => [result.strategy, result]))
  const previousMap = new Map((previousPayload.results ?? []).map((result) => [result.strategy, result]))
  const latestBest = latestPayload.recommendedOverall?.strategy ?? null
  const previousBest = previousPayload.recommendedOverall?.strategy ?? null
  const commonStrategies = [...latestMap.keys()].filter((strategy) => previousMap.has(strategy))
  const topImprovement = commonStrategies
    .map((strategy) => {
      const current = latestMap.get(strategy)!
      const before = previousMap.get(strategy)!
      return {
        strategy,
        exactMatchDelta: current.exactMatchRate - before.exactMatchRate,
        stpDelta: current.straightThroughRate - before.straightThroughRate,
        costDelta: current.estimatedCostPerDocument - before.estimatedCostPerDocument,
      }
    })
    .sort((left, right) => right.exactMatchDelta - left.exactMatchDelta)[0]

  return {
    action: latest.action,
    latestId: latest.id,
    previousId: previous.id,
    latestCreatedAt: latest.createdAt,
    previousCreatedAt: previous.createdAt,
    summary: [
      `Recommended strategy changed from ${previousBest ?? 'none'} to ${latestBest ?? 'none'}.`,
      topImprovement
        ? `Best exact-match delta: ${topImprovement.strategy} (${topImprovement.exactMatchDelta.toFixed(4)}).`
        : 'No comparable strategies found.',
    ],
    metrics: {
      latestRecommendedStrategy: latestBest,
      previousRecommendedStrategy: previousBest,
      bestImprovementStrategy: topImprovement?.strategy ?? null,
      bestImprovementExactMatchDelta: topImprovement?.exactMatchDelta ?? null,
      bestImprovementStpDelta: topImprovement?.stpDelta ?? null,
      bestImprovementCostDelta: topImprovement?.costDelta ?? null,
    },
  }
}

function compareOcrCostSnapshots(latest: OpsAuditRecord, previous: OpsAuditRecord): SnapshotComparisonResult {
  const latestPayload = latest.payload as {
    totals?: {
      documentsProcessed?: number
      estimatedTotalCost?: number
      estimatedCostPerDocument?: number
      totalOpenaiFields?: number
      premiumEscalationRate?: number
    }
  }
  const previousPayload = previous.payload as {
    totals?: {
      documentsProcessed?: number
      estimatedTotalCost?: number
      estimatedCostPerDocument?: number
      totalOpenaiFields?: number
      premiumEscalationRate?: number
    }
  }

  const latestTotals = latestPayload.totals ?? {}
  const previousTotals = previousPayload.totals ?? {}
  const costPerDocDelta = (latestTotals.estimatedCostPerDocument ?? 0) - (previousTotals.estimatedCostPerDocument ?? 0)
  const openaiFieldsDelta = (latestTotals.totalOpenaiFields ?? 0) - (previousTotals.totalOpenaiFields ?? 0)
  const premiumRateDelta = (latestTotals.premiumEscalationRate ?? 0) - (previousTotals.premiumEscalationRate ?? 0)

  return {
    action: latest.action,
    latestId: latest.id,
    previousId: previous.id,
    latestCreatedAt: latest.createdAt,
    previousCreatedAt: previous.createdAt,
    summary: [
      `Estimated cost/doc delta ${costPerDocDelta.toFixed(4)}.`,
      `OpenAI adjudication fields delta ${openaiFieldsDelta}.`,
      `Premium escalation rate delta ${premiumRateDelta.toFixed(4)}.`,
    ],
    metrics: {
      latestEstimatedCostPerDocument: latestTotals.estimatedCostPerDocument ?? null,
      previousEstimatedCostPerDocument: previousTotals.estimatedCostPerDocument ?? null,
      estimatedCostPerDocumentDelta: costPerDocDelta,
      latestTotalOpenaiFields: latestTotals.totalOpenaiFields ?? null,
      previousTotalOpenaiFields: previousTotals.totalOpenaiFields ?? null,
      totalOpenaiFieldsDelta: openaiFieldsDelta,
      latestPremiumEscalationRate: latestTotals.premiumEscalationRate ?? null,
      previousPremiumEscalationRate: previousTotals.premiumEscalationRate ?? null,
      premiumEscalationRateDelta: premiumRateDelta,
    },
  }
}

export function compareOperationalSnapshots(records: OpsAuditRecord[], action: string): SnapshotComparisonResult | null {
  const candidates = records
    .filter((record) => record.action === action)
    .sort((left, right) => new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime())

  if (candidates.length < 2) {
    return null
  }

  const [latest, previous] = candidates
  if (action === 'snapshot.learning_loop') {
    return compareLearningLoopSnapshots(latest, previous)
  }
  if (action === 'snapshot.routing_benchmark') {
    return compareRoutingSnapshots(latest, previous)
  }
  if (action === 'snapshot.ocr_costs') {
    return compareOcrCostSnapshots(latest, previous)
  }

  return {
    action,
    latestId: latest.id,
    previousId: previous.id,
    latestCreatedAt: latest.createdAt,
    previousCreatedAt: previous.createdAt,
    summary: ['No specialized comparator available for this snapshot type.'],
    metrics: {},
  }
}
