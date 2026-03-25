import type { DocumentRecord } from '@ocr/shared'

type TenantProcessingRule = {
  tenantId?: string
  family?: string
  country?: string
  visualEngine?: string | null
  decisionProfile?: string | null
  structuredMode?: string | null
  ensembleMode?: string | null
  ensembleEngines?: string | null
  fieldAdjudicationMode?: string | null
}

type TenantProcessingConfig = {
  defaults?: {
    visualEngine?: string | null
    decisionProfile?: string | null
    structuredMode?: string | null
    ensembleMode?: string | null
    ensembleEngines?: string | null
    fieldAdjudicationMode?: string | null
  }
  rules?: TenantProcessingRule[]
}

function getConfig(): TenantProcessingConfig {
  const raw = process.env.OCR_TENANT_PROCESSING_CONFIG
  if (!raw) {
    return {
        defaults: {
          visualEngine: process.env.OCR_DEFAULT_VISUAL_ENGINE ?? 'auto',
          decisionProfile: process.env.OCR_DEFAULT_DECISION_PROFILE ?? 'balanced',
          structuredMode: process.env.OCR_DEFAULT_STRUCTURED_MODE ?? 'auto',
          ensembleMode: process.env.OCR_DEFAULT_ENSEMBLE_MODE ?? 'always',
          ensembleEngines: process.env.OCR_DEFAULT_ENSEMBLE_ENGINES ?? 'rapidocr,google-documentai',
          fieldAdjudicationMode: process.env.OCR_DEFAULT_FIELD_ADJUDICATION_MODE ?? 'auto',
        },
        rules: []
      }
  }

  try {
    return JSON.parse(raw) as TenantProcessingConfig
  } catch {
    return {
        defaults: {
          visualEngine: process.env.OCR_DEFAULT_VISUAL_ENGINE ?? 'auto',
          decisionProfile: process.env.OCR_DEFAULT_DECISION_PROFILE ?? 'balanced',
          structuredMode: process.env.OCR_DEFAULT_STRUCTURED_MODE ?? 'auto',
          ensembleMode: process.env.OCR_DEFAULT_ENSEMBLE_MODE ?? 'always',
          ensembleEngines: process.env.OCR_DEFAULT_ENSEMBLE_ENGINES ?? 'rapidocr,google-documentai',
          fieldAdjudicationMode: process.env.OCR_DEFAULT_FIELD_ADJUDICATION_MODE ?? 'auto',
        },
        rules: []
      }
  }
}

export function resolveTenantProcessingOptions(document: DocumentRecord) {
  const config = getConfig()
  const matchingRule = (config.rules ?? []).find((rule) => {
    if (rule.tenantId && rule.tenantId !== document.tenantId) return false
    if (rule.family && rule.family !== document.documentFamily) return false
    if (rule.country && rule.country !== document.country) return false
    return true
  })

  return {
    visualEngine: matchingRule?.visualEngine ?? config.defaults?.visualEngine ?? null,
    decisionProfile: matchingRule?.decisionProfile ?? config.defaults?.decisionProfile ?? 'balanced',
    structuredMode: matchingRule?.structuredMode ?? config.defaults?.structuredMode ?? 'auto',
    ensembleMode: matchingRule?.ensembleMode ?? config.defaults?.ensembleMode ?? null,
    ensembleEngines: matchingRule?.ensembleEngines ?? config.defaults?.ensembleEngines ?? null,
    fieldAdjudicationMode: matchingRule?.fieldAdjudicationMode ?? config.defaults?.fieldAdjudicationMode ?? null,
  }
}
