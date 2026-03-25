import type { DocumentRecord } from '@ocr/shared'

import { getAllDocuments } from '@/lib/document-store'
import { runRemoteProcessing } from '@/lib/ocr-api'
import { recordOpsAuditEvent } from '@/lib/ops-audit'
import { ensureRouteAccessJson } from '@/lib/route-auth'
import {
  estimateProcessingCost,
  listRoutingStrategies,
  recommendRoutingStrategy,
  resolveAdaptiveRoutingStrategy,
  type RoutingBenchmarkSummary,
  type RoutingStrategyName,
} from '@/lib/routing-benchmark'
import { buildGoldenSet, evaluateDocumentAgainstGoldenEntry, getReviewedDocuments } from '@/lib/training-dataset'

type MutablePackMetric = {
  packId: string
  family: string
  country: string
  variant: string | null
  documentsProcessed: number
  totalFields: number
  matchedFields: number
  straightThroughCount: number
  reviewCount: number
  totalAgreement: number
  consensusFields: number
  totalCost: number
}

type RoutingBenchmarkResult = {
  strategy: RoutingStrategyName
  label: string
  description: string
  documents: Array<{
    documentId: string
    filename: string
    packId: string | null
    decision: DocumentRecord['decision']
    globalConfidence: number | null
    averageAgreement: number | null
    estimatedCost: number
    enginesExecuted: string[]
    exactMatchRate: number
    matchedFields: number
    totalFields: number
    mismatches: ReturnType<typeof evaluateDocumentAgainstGoldenEntry>['mismatches']
  }>
  documentsProcessed: number
  exactMatchRate: number
  straightThroughRate: number
  reviewRate: number
  averageConfidence: number
  averageAgreement: number
  estimatedCostPerDocument: number
  estimatedTotalCost: number
  byDecision: Record<DocumentRecord['decision'], number>
  packMetrics: Array<ReturnType<typeof finalizePackMetric>>
}

function createPackMetric(document: DocumentRecord): MutablePackMetric {
  return {
    packId: document.processingMetadata.packId ?? `${document.documentFamily}-${document.country}-${document.variant ?? 'generic'}`,
    family: document.documentFamily,
    country: document.country,
    variant: document.variant,
    documentsProcessed: 0,
    totalFields: 0,
    matchedFields: 0,
    straightThroughCount: 0,
    reviewCount: 0,
    totalAgreement: 0,
    consensusFields: 0,
    totalCost: 0,
  }
}

function finalizePackMetric(metric: MutablePackMetric) {
  return {
    packId: metric.packId,
    family: metric.family,
    country: metric.country,
    variant: metric.variant,
    documentsProcessed: metric.documentsProcessed,
    exactMatchRate: metric.totalFields ? metric.matchedFields / metric.totalFields : 0,
    straightThroughRate: metric.documentsProcessed ? metric.straightThroughCount / metric.documentsProcessed : 0,
    reviewRate: metric.documentsProcessed ? metric.reviewCount / metric.documentsProcessed : 0,
    averageAgreement: metric.consensusFields ? metric.totalAgreement / metric.consensusFields : 0,
    estimatedCostPerDocument: metric.documentsProcessed ? metric.totalCost / metric.documentsProcessed : 0,
  }
}

export async function GET(request: Request) {
  const unauthorized = await ensureRouteAccessJson()
  if (unauthorized) return unauthorized

  const { searchParams } = new URL(request.url)
  const strategyNames = (searchParams.get('strategies') ?? 'local_only,local_google,local_azure,certificate_local_support,ensemble_adjudicator,adaptive_hybrid')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean)
  const decisionProfile = searchParams.get('decision_profile') ?? 'balanced'
  const limit = Math.max(1, Number(searchParams.get('limit') ?? '5'))
  const persist = searchParams.get('persist') === '1'

  const strategies = listRoutingStrategies(strategyNames)
  const documents = await getAllDocuments()
  const reviewed = getReviewedDocuments(documents).slice(0, limit)
  const goldenSet = buildGoldenSet(reviewed)
  const benchmarkResults: RoutingBenchmarkResult[] = []

  for (const strategy of strategies) {
    let totalFields = 0
    let matchedFields = 0
    let totalConfidence = 0
    let processedDocuments = 0
    let totalAgreement = 0
    let consensusFields = 0
    let totalCost = 0
    const byDecision = {
      auto_accept: 0,
      accept_with_warning: 0,
      human_review: 0,
      reject: 0,
      pending: 0,
    }
    const documentsResult = []
    const packMetrics = new Map<string, MutablePackMetric>()

    for (const document of reviewed) {
      const goldenEntry = goldenSet.find((entry) => entry.documentId === document.id)
      if (!goldenEntry) continue

      const appliedStrategy = strategy.name === 'adaptive_hybrid' ? resolveAdaptiveRoutingStrategy(document).strategy : strategy

      const remotePartial = await runRemoteProcessing(document, {
        visualEngine: appliedStrategy.visualEngine,
        decisionProfile,
        structuredMode: appliedStrategy.structuredMode,
        ensembleMode: appliedStrategy.ensembleMode,
        ensembleEngines: appliedStrategy.ensembleEngines,
        fieldAdjudicationMode: appliedStrategy.fieldAdjudicationMode,
      })
      const candidate = {
        ...document,
        ...remotePartial,
      } as DocumentRecord
      const evaluation = evaluateDocumentAgainstGoldenEntry(candidate, goldenEntry)
      const fieldConsensuses = candidate.extractedFields.map((field) => field.consensus).filter((value) => value != null)
      const cost = estimateProcessingCost(candidate)
      const packKey = candidate.processingMetadata.packId ?? `${candidate.documentFamily}-${candidate.country}-${candidate.variant ?? 'generic'}`
      const packMetric = packMetrics.get(packKey) ?? createPackMetric(candidate)

      processedDocuments += 1
      totalFields += evaluation.totalFields
      matchedFields += evaluation.matchedFields
      totalConfidence += candidate.globalConfidence ?? 0
      totalAgreement += fieldConsensuses.reduce((acc, consensus) => acc + consensus.agreementRatio, 0)
      consensusFields += fieldConsensuses.length
      totalCost += cost.totalCost
      byDecision[candidate.decision] += 1

      packMetric.documentsProcessed += 1
      packMetric.totalFields += evaluation.totalFields
      packMetric.matchedFields += evaluation.matchedFields
      packMetric.totalAgreement += fieldConsensuses.reduce((acc, consensus) => acc + consensus.agreementRatio, 0)
      packMetric.consensusFields += fieldConsensuses.length
      packMetric.totalCost += cost.totalCost
      if (candidate.decision === 'auto_accept' || candidate.decision === 'accept_with_warning') packMetric.straightThroughCount += 1
      if (candidate.decision === 'human_review') packMetric.reviewCount += 1
      packMetrics.set(packKey, packMetric)

      documentsResult.push({
        documentId: document.id,
        filename: document.filename,
        packId: candidate.processingMetadata.packId,
        decision: candidate.decision,
        globalConfidence: candidate.globalConfidence,
        averageAgreement: fieldConsensuses.length
          ? fieldConsensuses.reduce((acc, consensus) => acc + consensus.agreementRatio, 0) / fieldConsensuses.length
          : null,
        estimatedCost: cost.totalCost,
        enginesExecuted: cost.executedEngines,
        exactMatchRate: evaluation.exactMatchRate,
        matchedFields: evaluation.matchedFields,
        totalFields: evaluation.totalFields,
        mismatches: evaluation.mismatches,
      })
    }

    const straightThroughCount = byDecision.auto_accept + byDecision.accept_with_warning
    benchmarkResults.push({
      strategy: strategy.name,
      label: strategy.label,
      description: strategy.description,
      documents: documentsResult,
      documentsProcessed: processedDocuments,
      exactMatchRate: totalFields ? matchedFields / totalFields : 0,
      straightThroughRate: processedDocuments ? straightThroughCount / processedDocuments : 0,
      reviewRate: processedDocuments ? byDecision.human_review / processedDocuments : 0,
      averageConfidence: processedDocuments ? totalConfidence / processedDocuments : 0,
      averageAgreement: consensusFields ? totalAgreement / consensusFields : 0,
      estimatedCostPerDocument: processedDocuments ? totalCost / processedDocuments : 0,
      estimatedTotalCost: totalCost,
      byDecision,
      packMetrics: [...packMetrics.values()].map(finalizePackMetric),
    })
  }

  const summaryForRecommendation: RoutingBenchmarkSummary[] = benchmarkResults.map((result) => ({
    strategy: result.strategy,
    label: result.label,
    exactMatchRate: result.exactMatchRate,
    straightThroughRate: result.straightThroughRate,
    averageAgreement: result.averageAgreement,
    reviewRate: result.reviewRate,
    estimatedCostPerDocument: result.estimatedCostPerDocument,
  }))

  const recommendedOverall = recommendRoutingStrategy(summaryForRecommendation)
  const allPackIds = [...new Set(benchmarkResults.flatMap((result) => result.packMetrics.map((metric) => metric.packId)))]
  const recommendedByPack = allPackIds.map((packId) => {
    const summaries = benchmarkResults
      .map((result) => {
        const metric = result.packMetrics.find((entry: ReturnType<typeof finalizePackMetric>) => entry.packId === packId)
        if (!metric) return null
        return {
          strategy: result.strategy,
          label: result.label,
          exactMatchRate: metric.exactMatchRate,
          straightThroughRate: metric.straightThroughRate,
          averageAgreement: metric.averageAgreement,
          reviewRate: metric.reviewRate,
          estimatedCostPerDocument: metric.estimatedCostPerDocument,
        } satisfies RoutingBenchmarkSummary
      })
      .filter((entry): entry is RoutingBenchmarkSummary => entry != null)

    return {
      packId,
      recommendation: recommendRoutingStrategy(summaries),
    }
  })

  const payload = {
    reviewedDocuments: reviewed.length,
    decisionProfile,
    strategies: strategies.map((strategy) => ({
      name: strategy.name,
      label: strategy.label,
      description: strategy.description,
      structuredMode: strategy.structuredMode,
    })),
    recommendedOverall,
    recommendedByPack,
    results: benchmarkResults,
  }

  let persistedSnapshotId: string | null = null
  if (persist) {
    const audit = await recordOpsAuditEvent({
      action: 'snapshot.routing_benchmark',
      payload,
    })
    persistedSnapshotId = audit.id
  }

  return Response.json({
    ...payload,
    persistedSnapshotId,
  })
}
