import type { DocumentRecord } from '@ocr/shared'

export type RoutingStrategyName = 'local_only' | 'local_google' | 'local_azure' | 'certificate_local_support' | 'ensemble_adjudicator' | 'adaptive_hybrid' | 'tenant_default'

export type RoutingStrategyConfig = {
  name: RoutingStrategyName
  label: string
  description: string
  visualEngine: string | null
  ensembleMode: string | null
  ensembleEngines: string | null
  fieldAdjudicationMode: string | null
  structuredMode: 'heuristic' | 'auto' | 'openai' | null
}

export type LiveRoutingDecision = {
  strategy: RoutingStrategyConfig
  reasons: string[]
}

export type RoutingBenchmarkSummary = {
  strategy: RoutingStrategyName
  label: string
  exactMatchRate: number
  straightThroughRate: number
  averageAgreement: number
  reviewRate: number
  estimatedCostPerDocument: number
}

export type RoutingRecommendation = {
  strategy: RoutingStrategyName
  label: string
  score: number
  reasons: string[]
}

type AdaptiveRoutingRule = {
  family?: DocumentRecord['documentFamily']
  country?: string
  mimeType?: string
  variant?: string | null
  packId?: string | null
  riskLevel?: DocumentRecord['riskLevel']
  minAttempts?: number
  requireFailedLatestJob?: boolean
  strategy: RoutingStrategyName
  reason: string
}

const DEFAULT_ENGINE_COSTS: Record<string, number> = {
  rapidocr: 0.0015,
  paddleocr: 0.002,
  doctr: 0.003,
  'google-documentai': 0.05,
  'azure-document-intelligence': 0.045,
  openaiField: 0.0035,
}

export const ROUTING_STRATEGIES: RoutingStrategyConfig[] = [
  {
    name: 'local_only',
    label: 'Local only',
    description: 'Solo RapidOCR local, sin adjudicacion.',
    visualEngine: 'rapidocr',
    ensembleMode: 'single',
    ensembleEngines: 'rapidocr',
    fieldAdjudicationMode: 'off',
    structuredMode: 'heuristic',
  },
  {
    name: 'local_google',
    label: 'Local + Google',
    description: 'RapidOCR mas Google Document AI con adjudicacion deterministica.',
    visualEngine: 'auto',
    ensembleMode: 'always',
    ensembleEngines: 'rapidocr,google-documentai',
    fieldAdjudicationMode: 'deterministic',
    structuredMode: 'auto',
  },
  {
    name: 'local_azure',
    label: 'Local + Azure',
    description: 'RapidOCR mas Azure Document Intelligence con adjudicacion deterministica.',
    visualEngine: 'auto',
    ensembleMode: 'always',
    ensembleEngines: 'rapidocr,azure-document-intelligence',
    fieldAdjudicationMode: 'deterministic',
    structuredMode: 'auto',
  },
  {
    name: 'certificate_local_support',
    label: 'Certificate local support',
    description: 'Certificados PDF con OCR local y normalizacion auto; premium solo si el pipeline lo exige despues.',
    visualEngine: 'auto',
    ensembleMode: 'always',
    ensembleEngines: 'rapidocr',
    fieldAdjudicationMode: 'deterministic',
    structuredMode: 'auto',
  },
  {
    name: 'ensemble_adjudicator',
    label: 'Ensemble + adjudicator',
    description: 'RapidOCR, Google y Azure en paralelo con adjudicacion por campo.',
    visualEngine: 'auto',
    ensembleMode: 'always',
    ensembleEngines: 'rapidocr,google-documentai,azure-document-intelligence',
    fieldAdjudicationMode: 'auto',
    structuredMode: 'auto',
  },
  {
    name: 'adaptive_hybrid',
    label: 'Adaptive hybrid',
    description: 'Selecciona ruta segun familia, riesgo y senales previas del documento.',
    visualEngine: 'auto',
    ensembleMode: 'always',
    ensembleEngines: 'rapidocr,google-documentai',
    fieldAdjudicationMode: 'auto',
    structuredMode: 'auto',
  },
]

const DEFAULT_ADAPTIVE_RULES: AdaptiveRoutingRule[] = [
  {
    family: 'passport',
    strategy: 'ensemble_adjudicator',
    reason: 'Pasaporte: se prioriza MRZ, cross-check y adjudicacion fuerte.',
  },
  {
    riskLevel: 'high',
    strategy: 'ensemble_adjudicator',
    reason: 'Documento de alto riesgo: se usa ensemble completo.',
  },
  {
    minAttempts: 2,
    strategy: 'ensemble_adjudicator',
    reason: 'Reintentos previos: se fuerza ensemble completo para evitar repetir fallos baratos.',
  },
  {
    requireFailedLatestJob: true,
    strategy: 'ensemble_adjudicator',
    reason: 'Ultimo intento fallido: se escala a ensemble completo.',
  },
  {
    family: 'driver_license',
    strategy: 'local_azure',
    reason: 'Licencia: se favorece Azure como unico premium por labels y vigencia.',
  },
  {
    family: 'identity',
    country: 'CL',
    strategy: 'local_google',
    reason: 'Identidad CL: ruta local+Google con normalizacion automatica conservadora.',
  },
  {
    family: 'identity',
    country: 'PE',
    strategy: 'local_google',
    reason: 'Identidad PE: ruta local+Google con normalizacion automatica conservadora.',
  },
  {
    family: 'identity',
    country: 'CO',
    strategy: 'local_google',
    reason: 'Identidad CO: ruta local+Google con normalizacion automatica conservadora.',
  },
  {
    family: 'certificate',
    country: 'CL',
    mimeType: 'application/pdf',
    strategy: 'certificate_local_support',
    reason: 'Certificado PDF CL: se prioriza embedded text y rescate local antes de premium.',
  },
]

function parseAdaptiveRoutingRules() {
  const raw = process.env.OCR_ADAPTIVE_ROUTING_CONFIG
  if (!raw) return DEFAULT_ADAPTIVE_RULES

  try {
    const parsed = JSON.parse(raw) as { rules?: AdaptiveRoutingRule[] }
    const rules = parsed.rules?.filter((rule) => resolveRoutingStrategy(rule.strategy) != null)
    return rules && rules.length > 0 ? rules : DEFAULT_ADAPTIVE_RULES
  } catch {
    return DEFAULT_ADAPTIVE_RULES
  }
}

function normalizeEngineName(value: string | null | undefined) {
  return (value ?? '').trim().toLowerCase()
}

function configuredEngineCosts(): Record<string, number> {
  return {
    rapidocr: Number(process.env.OCR_COST_RAPIDOCR ?? DEFAULT_ENGINE_COSTS.rapidocr),
    paddleocr: Number(process.env.OCR_COST_PADDLEOCR ?? DEFAULT_ENGINE_COSTS.paddleocr),
    doctr: Number(process.env.OCR_COST_DOCTR ?? DEFAULT_ENGINE_COSTS.doctr),
    'google-documentai': Number(process.env.OCR_COST_GOOGLE_DOCUMENTAI ?? DEFAULT_ENGINE_COSTS['google-documentai']),
    'azure-document-intelligence': Number(process.env.OCR_COST_AZURE_DOCUMENT_INTELLIGENCE ?? DEFAULT_ENGINE_COSTS['azure-document-intelligence']),
    openaiField: Number(process.env.OCR_COST_OPENAI_FIELD_ADJUDICATION ?? DEFAULT_ENGINE_COSTS.openaiField),
  }
}

function matchesAdaptiveRule(
  rule: AdaptiveRoutingRule,
  document: Pick<DocumentRecord, 'documentFamily' | 'country' | 'riskLevel' | 'mimeType' | 'variant' | 'latestJob' | 'processingMetadata'>,
  previousAttempts: number,
  latestFailed: boolean
) {
  if (rule.family && rule.family !== document.documentFamily) return false
  if (rule.country && rule.country !== document.country) return false
  if (rule.mimeType && rule.mimeType !== document.mimeType) return false
  if (rule.variant !== undefined && rule.variant !== document.variant) return false
  if (rule.packId !== undefined && rule.packId !== (document.processingMetadata.packId ?? null)) return false
  if (rule.riskLevel && rule.riskLevel !== document.riskLevel) return false
  if (rule.minAttempts != null && previousAttempts < rule.minAttempts) return false
  if (rule.requireFailedLatestJob && !latestFailed) return false
  return true
}

export function resolveRoutingStrategy(name: string): RoutingStrategyConfig | null {
  return ROUTING_STRATEGIES.find((strategy) => strategy.name === name) ?? null
}

export function listRoutingStrategies(names?: string[]) {
  if (!names || names.length === 0) return ROUTING_STRATEGIES
  return names
    .map((name) => resolveRoutingStrategy(name))
    .filter((strategy): strategy is RoutingStrategyConfig => strategy != null)
}

export function estimateProcessingCost(document: Pick<DocumentRecord, 'processingMetadata' | 'extractedFields'>) {
  const costs = configuredEngineCosts()
  const executedEngines = new Set(
    document.processingMetadata.ocrRuns
      .map((run) => normalizeEngineName(run.engine || run.source))
      .filter(Boolean)
  )

  const engineCost = [...executedEngines].reduce((acc, engine) => acc + (costs[engine] ?? 0), 0)
  const openaiFieldCount = document.extractedFields.filter((field) => field.adjudication?.method === 'openai').length
  const adjudicationCost = openaiFieldCount * costs.openaiField

  return {
    executedEngines: [...executedEngines],
    openaiFieldCount,
    engineCost,
    adjudicationCost,
    totalCost: engineCost + adjudicationCost,
  }
}

export function recommendRoutingStrategy(results: RoutingBenchmarkSummary[]): RoutingRecommendation | null {
  if (results.length === 0) return null

  const maxCost = Math.max(...results.map((result) => result.estimatedCostPerDocument), 0)
  const scored = results.map((result) => {
    const qualityScore =
      (result.exactMatchRate * 0.6) +
      (result.straightThroughRate * 0.2) +
      (result.averageAgreement * 0.15) +
      ((1 - result.reviewRate) * 0.05)
    const normalizedCost = maxCost > 0 ? result.estimatedCostPerDocument / maxCost : 0
    const score = qualityScore - (normalizedCost * 0.12)
    return {
      ...result,
      score,
    }
  })

  scored.sort((left, right) => right.score - left.score)
  const best = scored[0]
  const cheapest = [...results].sort((left, right) => left.estimatedCostPerDocument - right.estimatedCostPerDocument)[0]
  const reasons = [
    `Exact match ${Math.round(best.exactMatchRate * 100)}% con STP ${Math.round(best.straightThroughRate * 100)}%.`,
    `Costo estimado/doc ${best.estimatedCostPerDocument.toFixed(4)}.`,
  ]

  if (cheapest && cheapest.strategy !== best.strategy) {
    const costGap = best.estimatedCostPerDocument - cheapest.estimatedCostPerDocument
    reasons.push(`Supera a la opcion mas barata con delta de costo ${costGap.toFixed(4)} por documento.`)
  }

  return {
    strategy: best.strategy,
    label: best.label,
    score: best.score,
    reasons,
  }
}

export function resolveAdaptiveRoutingStrategy(document: Pick<DocumentRecord, 'documentFamily' | 'country' | 'riskLevel' | 'mimeType' | 'variant' | 'latestJob' | 'processingMetadata'>): LiveRoutingDecision {
  const reasons: string[] = []
  const previousAttempts = document.latestJob?.attemptCount ?? 0
  const latestFailed = document.latestJob?.status === 'failed'

  for (const rule of parseAdaptiveRoutingRules()) {
    if (!matchesAdaptiveRule(rule, document, previousAttempts, latestFailed)) continue
    reasons.push(rule.reason)
    return {
      strategy: resolveRoutingStrategy(rule.strategy) ?? ROUTING_STRATEGIES[0],
      reasons,
    }
  }

  reasons.push('Fallback adaptativo por defecto: ruta hibrida balanceada.')
  return {
    strategy: resolveRoutingStrategy('adaptive_hybrid') ?? ROUTING_STRATEGIES[5],
    reasons,
  }
}
