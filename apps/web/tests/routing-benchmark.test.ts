import test from 'node:test'
import assert from 'node:assert/strict'

import type { DocumentRecord } from '@ocr/shared'
import { estimateProcessingCost, recommendRoutingStrategy, resolveAdaptiveRoutingStrategy } from '../src/lib/routing-benchmark.ts'

const sampleDocument = {
  processingMetadata: {
    ocrRuns: [
      {
        engine: 'rapidocr',
        source: 'rapidocr',
      },
      {
        engine: 'google-documentai',
        source: 'google-documentai',
      },
    ],
  },
  extractedFields: [
    {
      adjudication: {
        method: 'openai',
      },
    },
    {
      adjudication: {
        method: 'deterministic',
      },
    },
  ],
} as Pick<DocumentRecord, 'processingMetadata' | 'extractedFields'>

const emptyProcessingMetadata: DocumentRecord['processingMetadata'] = {
  packId: null,
  packVersion: null,
  documentSide: null,
  crossSideDetected: false,
  routingStrategy: null,
  routingReasons: [],
  decisionProfile: null,
  requestedVisualEngine: null,
  selectedVisualEngine: null,
  ensembleMode: null,
  classificationConfidence: null,
  extractionSource: null,
  processingEngine: null,
  ocrRuns: [],
  adjudicationMode: null,
  adjudicatedFields: 0,
  adjudicationAbstentions: 0,
  processingTrace: [],
}

test('estimateProcessingCost sums OCR engines and openai field adjudication', () => {
  const estimated = estimateProcessingCost(sampleDocument)
  assert.deepEqual(estimated.executedEngines.sort(), ['google-documentai', 'rapidocr'])
  assert.equal(estimated.openaiFieldCount, 1)
  assert.equal(Number(estimated.totalCost.toFixed(4)), 0.055)
})

test('recommendRoutingStrategy balances quality against cost', () => {
  const recommendation = recommendRoutingStrategy([
    {
      strategy: 'local_google',
      label: 'Local + Google',
      exactMatchRate: 0.98,
      straightThroughRate: 0.9,
      averageAgreement: 0.9,
      reviewRate: 0.08,
      estimatedCostPerDocument: 0.052,
    },
    {
      strategy: 'ensemble_adjudicator',
      label: 'Ensemble + adjudicator',
      exactMatchRate: 0.99,
      straightThroughRate: 0.92,
      averageAgreement: 0.95,
      reviewRate: 0.05,
      estimatedCostPerDocument: 0.1,
    },
  ])

  assert.equal(recommendation?.strategy, 'local_google')
  assert.ok((recommendation?.reasons.length ?? 0) >= 2)
})

test('resolveAdaptiveRoutingStrategy escalates passports to full ensemble', () => {
  const document = {
    documentFamily: 'passport',
    country: 'CHL',
    variant: null,
    riskLevel: 'medium',
    mimeType: 'image/png',
    latestJob: null,
    processingMetadata: emptyProcessingMetadata,
  } as Pick<DocumentRecord, 'documentFamily' | 'country' | 'variant' | 'riskLevel' | 'mimeType' | 'latestJob' | 'processingMetadata'>

  const routing = resolveAdaptiveRoutingStrategy(document)
  assert.equal(routing.strategy.name, 'ensemble_adjudicator')
  assert.equal(routing.strategy.structuredMode, 'auto')
  assert.ok(routing.reasons[0].includes('Pasaporte'))
})

test('resolveAdaptiveRoutingStrategy keeps LatAm identity on local_google by default', () => {
  const document = {
    documentFamily: 'identity',
    country: 'CL',
    variant: 'identity-cl-front-text',
    riskLevel: 'medium',
    mimeType: 'image/jpeg',
    latestJob: null,
    processingMetadata: emptyProcessingMetadata,
  } as Pick<DocumentRecord, 'documentFamily' | 'country' | 'variant' | 'riskLevel' | 'mimeType' | 'latestJob' | 'processingMetadata'>

  const routing = resolveAdaptiveRoutingStrategy(document)
  assert.equal(routing.strategy.name, 'local_google')
})

test('resolveAdaptiveRoutingStrategy keeps certificate PDF on local support route', () => {
  const document = {
    documentFamily: 'certificate',
    country: 'CL',
    variant: 'certificate-cl-previsional-text',
    riskLevel: 'medium',
    mimeType: 'application/pdf',
    latestJob: null,
    processingMetadata: {
      ...emptyProcessingMetadata,
      packId: 'certificate-cl-previsional',
    },
  } as Pick<DocumentRecord, 'documentFamily' | 'country' | 'variant' | 'riskLevel' | 'mimeType' | 'latestJob' | 'processingMetadata'>

  const routing = resolveAdaptiveRoutingStrategy(document)
  assert.equal(routing.strategy.name, 'certificate_local_support')
  assert.equal(routing.strategy.ensembleEngines, 'rapidocr')
  assert.equal(routing.strategy.structuredMode, 'auto')
})

test('resolveAdaptiveRoutingStrategy respects runtime override rules', () => {
  process.env.OCR_ADAPTIVE_ROUTING_CONFIG = JSON.stringify({
    rules: [
      {
        family: 'identity',
        country: 'CL',
        strategy: 'local_azure',
        reason: 'forced for test',
      },
    ],
  })
  try {
    const document = {
      documentFamily: 'identity',
      country: 'CL',
      variant: 'identity-cl-front-text',
      riskLevel: 'medium',
      mimeType: 'image/jpeg',
      latestJob: null,
      processingMetadata: emptyProcessingMetadata,
    } as Pick<DocumentRecord, 'documentFamily' | 'country' | 'variant' | 'riskLevel' | 'mimeType' | 'latestJob' | 'processingMetadata'>

    const routing = resolveAdaptiveRoutingStrategy(document)
    assert.equal(routing.strategy.name, 'local_azure')
  } finally {
    delete process.env.OCR_ADAPTIVE_ROUTING_CONFIG
  }
})
