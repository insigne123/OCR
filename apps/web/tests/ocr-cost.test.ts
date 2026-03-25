import test from 'node:test'
import assert from 'node:assert/strict'

import type { DocumentRecord } from '@ocr/shared'
import { buildOcrCostInsights } from '../src/lib/ocr-cost-insights.ts'
import { estimateProcessingCost } from '../src/lib/ocr-cost.ts'

function createDocument(overrides?: Partial<DocumentRecord>): DocumentRecord {
  return {
    id: 'doc-cost',
    tenantId: 'tenant-a',
    filename: 'demo.jpeg',
    mimeType: 'image/jpeg',
    size: 100,
    storagePath: 'uploads/demo.jpeg',
    storageProvider: 'local',
    sourceHash: null,
    status: 'completed',
    decision: 'auto_accept',
    documentFamily: 'identity',
    country: 'CL',
    variant: 'identity-cl-front-text',
    riskLevel: 'medium',
    issuer: null,
    holderName: null,
    pageCount: 1,
    globalConfidence: 0.98,
    reviewRequired: false,
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: '2026-01-01T00:00:00.000Z',
    processedAt: '2026-01-01T00:00:00.000Z',
    assumptions: [],
    issues: [],
    extractedFields: [],
    documentPages: [],
    reviewSessions: [],
    latestJob: null,
    processingMetadata: {
      packId: 'identity-cl-front',
      packVersion: null,
      documentSide: 'front',
      crossSideDetected: false,
      routingStrategy: 'local_google',
      routingReasons: [],
      decisionProfile: 'balanced',
      requestedVisualEngine: 'auto',
      selectedVisualEngine: 'rapidocr-local',
      ensembleMode: 'single',
      classificationConfidence: 0.99,
      extractionSource: 'rapidocr-local',
      processingEngine: 'heuristic-visual-ocr',
      ocrRuns: [
        {
          engine: 'rapidocr',
          source: 'rapidocr-local',
          success: true,
          selected: true,
          score: 0.9,
          pageCount: 1,
          text: 'demo',
          averageConfidence: 0.95,
          classificationFamily: 'identity',
          classificationCountry: 'CL',
          classificationConfidence: 0.99,
          supportedClassification: true,
          preprocessProfile: 'original',
          assumptions: [],
          pages: [],
          tokens: [],
          keyValuePairs: [],
          tableCandidateRows: [],
        },
      ],
      adjudicationMode: 'deterministic',
      adjudicatedFields: 0,
      adjudicationAbstentions: 0,
      processingTrace: [],
    },
    lastReviewedAt: null,
    reportSections: [],
    humanSummary: null,
    reportHtml: null,
    ...overrides,
  }
}

test('estimateProcessingCost adds engine and openai adjudication cost', () => {
  const document = createDocument({
    extractedFields: [
      {
        id: 'field-1',
        section: 'summary',
        fieldName: 'document_number',
        label: 'Numero',
        rawText: '12.345.678-5',
        normalizedValue: '12.345.678-5',
        valueType: 'text',
        confidence: 0.9,
        engine: 'ocr-api',
        pageNumber: 1,
        bbox: null,
        evidenceSpan: null,
        validationStatus: 'valid',
        reviewStatus: 'confirmed',
        isInferred: false,
        issueIds: [],
        candidates: [],
        consensus: null,
        adjudication: {
          method: 'openai',
          abstained: false,
          selectedValue: '12.345.678-5',
          selectedSource: 'google-documentai',
          selectedEngine: 'google-documentai',
          confidence: 0.95,
          rationale: 'demo',
          evidenceSources: ['google-documentai'],
        },
      },
    ],
    processingMetadata: {
      ...createDocument().processingMetadata,
      ocrRuns: [
        ...createDocument().processingMetadata.ocrRuns,
        {
          ...createDocument().processingMetadata.ocrRuns[0],
          engine: 'google-documentai',
          source: 'google-documentai',
          selected: false,
        },
      ],
    },
  })

  const estimated = estimateProcessingCost(document)
  assert.deepEqual(estimated.executedEngines.sort(), ['google-documentai', 'rapidocr'])
  assert.equal(estimated.openaiFieldCount, 1)
  assert.equal(Number(estimated.totalCost.toFixed(4)), 0.055)
})

test('buildOcrCostInsights aggregates routing and pack metrics', () => {
  const documents = [
    createDocument(),
    createDocument({
      id: 'doc-cost-2',
      decision: 'human_review',
      processingMetadata: {
        ...createDocument().processingMetadata,
        routingStrategy: 'ensemble_adjudicator',
        ocrRuns: [
          ...createDocument().processingMetadata.ocrRuns,
          {
            ...createDocument().processingMetadata.ocrRuns[0],
            engine: 'google-documentai',
            source: 'google-documentai',
            selected: false,
          },
        ],
      },
    }),
  ]

  const insight = buildOcrCostInsights(documents)
  assert.equal(insight.totals.documentsProcessed, 2)
  assert.equal(insight.byPack[0]?.packId, 'identity-cl-front')
  assert.equal(insight.byRoutingStrategy[0]?.strategy, 'ensemble_adjudicator')
  assert.ok(insight.totals.estimatedCostPerDocument > 0)
})
