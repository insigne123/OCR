import type { DocumentDecision, DocumentRecord } from '@ocr/shared'

const DEFAULT_ENGINE_COSTS = {
  rapidocr: 0.0015,
  paddleocr: 0.002,
  doctr: 0.003,
  'google-documentai': 0.05,
  'azure-document-intelligence': 0.045,
  openaiField: 0.0035,
}

type PackCostMetric = {
  packId: string
  family: string
  country: string
  variant: string | null
  documentsProcessed: number
  totalCost: number
  totalOpenaiFields: number
  premiumEscalations: number
  straightThroughCount: number
}

type RoutingCostMetric = {
  strategy: string
  documentsProcessed: number
  totalCost: number
  premiumEscalations: number
  totalOpenaiFields: number
}

type EngineCostMetric = {
  engine: string
  documentsProcessed: number
  estimatedCost: number
}

function createPackMetric(document: DocumentRecord): PackCostMetric {
  return {
    packId: document.processingMetadata.packId ?? `${document.documentFamily}-${document.country}-${document.variant ?? 'generic'}`,
    family: document.documentFamily,
    country: document.country,
    variant: document.variant,
    documentsProcessed: 0,
    totalCost: 0,
    totalOpenaiFields: 0,
    premiumEscalations: 0,
    straightThroughCount: 0,
  }
}

function finalizePackMetric(metric: PackCostMetric) {
  return {
    ...metric,
    estimatedCostPerDocument: metric.documentsProcessed ? metric.totalCost / metric.documentsProcessed : 0,
    straightThroughRate: metric.documentsProcessed ? metric.straightThroughCount / metric.documentsProcessed : 0,
  }
}

function finalizeRoutingMetric(metric: RoutingCostMetric) {
  return {
    ...metric,
    estimatedCostPerDocument: metric.documentsProcessed ? metric.totalCost / metric.documentsProcessed : 0,
  }
}

function finalizeEngineMetric(metric: EngineCostMetric) {
  return {
    ...metric,
    estimatedCostPerDocument: metric.documentsProcessed ? metric.estimatedCost / metric.documentsProcessed : 0,
  }
}

function isProcessedDecision(decision: DocumentDecision) {
  return decision !== 'pending'
}

function normalizeEngineName(value: string | null | undefined) {
  return (value ?? '').trim().toLowerCase()
}

function configuredEngineCosts() {
  return {
    rapidocr: Number(process.env.OCR_COST_RAPIDOCR ?? DEFAULT_ENGINE_COSTS.rapidocr),
    paddleocr: Number(process.env.OCR_COST_PADDLEOCR ?? DEFAULT_ENGINE_COSTS.paddleocr),
    doctr: Number(process.env.OCR_COST_DOCTR ?? DEFAULT_ENGINE_COSTS.doctr),
    'google-documentai': Number(process.env.OCR_COST_GOOGLE_DOCUMENTAI ?? DEFAULT_ENGINE_COSTS['google-documentai']),
    'azure-document-intelligence': Number(process.env.OCR_COST_AZURE_DOCUMENT_INTELLIGENCE ?? DEFAULT_ENGINE_COSTS['azure-document-intelligence']),
    openaiField: Number(process.env.OCR_COST_OPENAI_FIELD_ADJUDICATION ?? DEFAULT_ENGINE_COSTS.openaiField),
  }
}

function estimateProcessingCost(document: Pick<DocumentRecord, 'processingMetadata' | 'extractedFields'>) {
  const costs = configuredEngineCosts()
  const executedEngines = new Set(
    document.processingMetadata.ocrRuns
      .map((run) => normalizeEngineName(run.engine || run.source))
      .filter(Boolean)
  )
  const engineList = [...executedEngines]
  const premiumEngines = engineList.filter((engine) => engine === 'google-documentai' || engine === 'azure-document-intelligence')
  const engineCost = engineList.reduce((acc, engine) => acc + (costs[engine as keyof typeof costs] ?? 0), 0)
  const openaiFieldCount = document.extractedFields.filter((field) => field.adjudication?.method === 'openai').length
  const adjudicationCost = openaiFieldCount * costs.openaiField

  return {
    executedEngines: engineList,
    premiumEngines,
    openaiFieldCount,
    engineCost,
    adjudicationCost,
    totalCost: engineCost + adjudicationCost,
  }
}

export function buildOcrCostInsights(documents: DocumentRecord[]) {
  const engineCosts = configuredEngineCosts()
  const processed = documents.filter((document) => isProcessedDecision(document.decision))
  const packMetrics = new Map<string, PackCostMetric>()
  const routingMetrics = new Map<string, RoutingCostMetric>()
  const engineMetrics = new Map<string, EngineCostMetric>()
  let totalCost = 0
  let totalOpenaiFields = 0
  let premiumEscalationDocs = 0

  for (const document of processed) {
    const cost = estimateProcessingCost(document)
    const packKey = document.processingMetadata.packId ?? `${document.documentFamily}-${document.country}-${document.variant ?? 'generic'}`
    const routingStrategy = document.processingMetadata.routingStrategy ?? 'unknown'
    const packMetric = packMetrics.get(packKey) ?? createPackMetric(document)
    const routingMetric = routingMetrics.get(routingStrategy) ?? {
      strategy: routingStrategy,
      documentsProcessed: 0,
      totalCost: 0,
      premiumEscalations: 0,
      totalOpenaiFields: 0,
    }

    totalCost += cost.totalCost
    totalOpenaiFields += cost.openaiFieldCount
    if (cost.premiumEngines.length > 0) premiumEscalationDocs += 1

    packMetric.documentsProcessed += 1
    packMetric.totalCost += cost.totalCost
    packMetric.totalOpenaiFields += cost.openaiFieldCount
    packMetric.premiumEscalations += cost.premiumEngines.length > 0 ? 1 : 0
    if (document.decision === 'auto_accept' || document.decision === 'accept_with_warning') {
      packMetric.straightThroughCount += 1
    }
    packMetrics.set(packKey, packMetric)

    routingMetric.documentsProcessed += 1
    routingMetric.totalCost += cost.totalCost
    routingMetric.premiumEscalations += cost.premiumEngines.length > 0 ? 1 : 0
    routingMetric.totalOpenaiFields += cost.openaiFieldCount
    routingMetrics.set(routingStrategy, routingMetric)

    for (const engine of cost.executedEngines) {
      const entry = engineMetrics.get(engine) ?? { engine, documentsProcessed: 0, estimatedCost: 0 }
      entry.documentsProcessed += 1
      entry.estimatedCost += engineCosts[engine as keyof typeof engineCosts] ?? 0
      engineMetrics.set(engine, entry)
    }
  }

  const byPack = [...packMetrics.values()]
    .map(finalizePackMetric)
    .sort((left, right) => right.totalCost - left.totalCost)
  const byRoutingStrategy = [...routingMetrics.values()]
    .map(finalizeRoutingMetric)
    .sort((left, right) => right.totalCost - left.totalCost)
  const byEngine = [...engineMetrics.values()]
    .map(finalizeEngineMetric)
    .sort((left, right) => right.documentsProcessed - left.documentsProcessed)

  return {
    generatedAt: new Date().toISOString(),
    totals: {
      documentsProcessed: processed.length,
      estimatedTotalCost: totalCost,
      estimatedCostPerDocument: processed.length ? totalCost / processed.length : 0,
      totalOpenaiFields,
      premiumEscalationDocs,
      premiumEscalationRate: processed.length ? premiumEscalationDocs / processed.length : 0,
    },
    byPack,
    byRoutingStrategy,
    byEngine,
    topSavingsCandidates: byPack
      .filter((entry) => entry.documentsProcessed >= 1)
      .slice(0, 5)
      .map((entry) => ({
        packId: entry.packId,
        family: entry.family,
        estimatedCostPerDocument: entry.estimatedCostPerDocument,
        premiumEscalationRate: entry.documentsProcessed ? entry.premiumEscalations / entry.documentsProcessed : 0,
        openaiFieldsPerDocument: entry.documentsProcessed ? entry.totalOpenaiFields / entry.documentsProcessed : 0,
      })),
  }
}
