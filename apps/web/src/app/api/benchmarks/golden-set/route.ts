import type { DocumentRecord } from '@ocr/shared'
import { getAllDocuments } from '@/lib/document-store'
import { runRemoteProcessing } from '@/lib/ocr-api'
import { ensureRouteAccessJson } from '@/lib/route-auth'
import { buildGoldenSet, evaluateDocumentAgainstGoldenEntry, getReviewedDocuments } from '@/lib/training-dataset'

export async function GET(request: Request) {
  const unauthorized = await ensureRouteAccessJson()
  if (unauthorized) return unauthorized

  const { searchParams } = new URL(request.url)
  const engines = (searchParams.get('engines') ?? 'rapidocr')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean)
  const decisionProfile = searchParams.get('decision_profile') ?? 'balanced'
  const limit = Math.max(1, Number(searchParams.get('limit') ?? '5'))

  const documents = await getAllDocuments()
  const reviewed = getReviewedDocuments(documents).slice(0, limit)
  const goldenSet = buildGoldenSet(reviewed)

  const benchmarkResults = []
  for (const engine of engines) {
    let totalFields = 0
    let matchedFields = 0
    let totalConfidence = 0
    let processedDocuments = 0
    let totalAgreement = 0
    let consensusFields = 0
    let disagreementFields = 0
    const byDecision = {
      auto_accept: 0,
      accept_with_warning: 0,
      human_review: 0,
      reject: 0,
      pending: 0,
    }
    const documentsResult = []

    for (const document of reviewed) {
      const goldenEntry = goldenSet.find((entry) => entry.documentId === document.id)
      if (!goldenEntry) continue

      const remotePartial = await runRemoteProcessing(document, { visualEngine: engine, decisionProfile })
      const candidate = {
        ...document,
        ...remotePartial
      } as DocumentRecord
      processedDocuments += 1
      totalConfidence += candidate.globalConfidence ?? 0
      byDecision[candidate.decision] += 1
      const fieldConsensuses = candidate.extractedFields.map((field) => field.consensus).filter((value) => value != null)
      consensusFields += fieldConsensuses.length
      totalAgreement += fieldConsensuses.reduce((acc, consensus) => acc + consensus.agreementRatio, 0)
      disagreementFields += fieldConsensuses.filter((consensus) => consensus.disagreement).length
      const evaluation = evaluateDocumentAgainstGoldenEntry(candidate, goldenEntry)
      totalFields += evaluation.totalFields
      matchedFields += evaluation.matchedFields
      documentsResult.push({
        documentId: document.id,
        filename: document.filename,
        decision: candidate.decision,
        globalConfidence: candidate.globalConfidence,
        disagreementFields: fieldConsensuses.filter((consensus) => consensus.disagreement).length,
        averageAgreement: fieldConsensuses.length
          ? fieldConsensuses.reduce((acc, consensus) => acc + consensus.agreementRatio, 0) / fieldConsensuses.length
          : null,
        exactMatchRate: evaluation.exactMatchRate,
        matchedFields: evaluation.matchedFields,
        totalFields: evaluation.totalFields,
        mismatches: evaluation.mismatches
      })
    }

    const straightThroughCount = byDecision.auto_accept + byDecision.accept_with_warning

    benchmarkResults.push({
      engine,
      decisionProfile,
      documents: documentsResult,
      documentsProcessed: processedDocuments,
      totalFields,
      matchedFields,
      exactMatchRate: totalFields ? matchedFields / totalFields : 0,
      averageConfidence: processedDocuments ? totalConfidence / processedDocuments : 0,
      averageAgreement: consensusFields ? totalAgreement / consensusFields : 0,
      disagreementRate: consensusFields ? disagreementFields / consensusFields : 0,
      byDecision,
      straightThroughRate: processedDocuments ? straightThroughCount / processedDocuments : 0,
      reviewRate: processedDocuments ? byDecision.human_review / processedDocuments : 0,
      rejectRate: processedDocuments ? byDecision.reject / processedDocuments : 0,
    })
  }

  const leaderboard = [...benchmarkResults]
    .sort((left, right) => {
      if (right.exactMatchRate !== left.exactMatchRate) return right.exactMatchRate - left.exactMatchRate
      if (right.straightThroughRate !== left.straightThroughRate) return right.straightThroughRate - left.straightThroughRate
      return right.averageConfidence - left.averageConfidence
    })
    .map((result, index) => ({
      rank: index + 1,
      engine: result.engine,
      exactMatchRate: result.exactMatchRate,
      straightThroughRate: result.straightThroughRate,
      reviewRate: result.reviewRate,
      rejectRate: result.rejectRate,
      averageConfidence: result.averageConfidence,
      averageAgreement: result.averageAgreement,
      disagreementRate: result.disagreementRate,
      byDecision: result.byDecision,
    }))

  return Response.json({
    reviewedDocuments: reviewed.length,
    engines,
    decisionProfile,
    leaderboard,
    results: benchmarkResults
  })
}
