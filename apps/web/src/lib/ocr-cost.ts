import type { DocumentRecord } from '@ocr/shared'

export type OcrEngineCostConfig = {
  rapidocr: number
  paddleocr: number
  doctr: number
  'google-documentai': number
  'azure-document-intelligence': number
  openaiField: number
}

export type OcrCostBreakdown = {
  executedEngines: string[]
  premiumEngines: string[]
  openaiFieldCount: number
  engineCost: number
  adjudicationCost: number
  totalCost: number
}

export const DEFAULT_ENGINE_COSTS: OcrEngineCostConfig = {
  rapidocr: 0.0015,
  paddleocr: 0.002,
  doctr: 0.003,
  'google-documentai': 0.05,
  'azure-document-intelligence': 0.045,
  openaiField: 0.0035,
}

function normalizeEngineName(value: string | null | undefined) {
  return (value ?? '').trim().toLowerCase()
}

function toConfiguredNumber(value: string | undefined, fallback: number) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback
}

export function configuredEngineCosts(): OcrEngineCostConfig {
  return {
    rapidocr: toConfiguredNumber(process.env.OCR_COST_RAPIDOCR, DEFAULT_ENGINE_COSTS.rapidocr),
    paddleocr: toConfiguredNumber(process.env.OCR_COST_PADDLEOCR, DEFAULT_ENGINE_COSTS.paddleocr),
    doctr: toConfiguredNumber(process.env.OCR_COST_DOCTR, DEFAULT_ENGINE_COSTS.doctr),
    'google-documentai': toConfiguredNumber(process.env.OCR_COST_GOOGLE_DOCUMENTAI, DEFAULT_ENGINE_COSTS['google-documentai']),
    'azure-document-intelligence': toConfiguredNumber(process.env.OCR_COST_AZURE_DOCUMENT_INTELLIGENCE, DEFAULT_ENGINE_COSTS['azure-document-intelligence']),
    openaiField: toConfiguredNumber(process.env.OCR_COST_OPENAI_FIELD_ADJUDICATION, DEFAULT_ENGINE_COSTS.openaiField),
  }
}

export function estimateProcessingCost(document: Pick<DocumentRecord, 'processingMetadata' | 'extractedFields'>): OcrCostBreakdown {
  const costs = configuredEngineCosts()
  const executedEngines = new Set(
    document.processingMetadata.ocrRuns
      .map((run) => normalizeEngineName(run.engine || run.source))
      .filter(Boolean)
  )
  const engineList = [...executedEngines]
  const premiumEngines = engineList.filter((engine) => engine === 'google-documentai' || engine === 'azure-document-intelligence')
  const engineCost = engineList.reduce((acc, engine) => acc + (costs[engine as keyof OcrEngineCostConfig] ?? 0), 0)
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
