import test from 'node:test'
import assert from 'node:assert/strict'

import type { DocumentRecord } from '@ocr/shared'
import { resolveTenantProcessingOptions } from '../src/lib/tenant-processing.ts'

const document: DocumentRecord = {
  id: 'doc-3',
  tenantId: 'tenant-a',
  filename: 'demo.pdf',
  mimeType: 'application/pdf',
  size: 100,
  storagePath: 'uploads/demo.pdf',
  storageProvider: 'local',
  sourceHash: null,
  status: 'uploaded',
  decision: 'pending',
  documentFamily: 'identity',
  country: 'CL',
  variant: null,
  riskLevel: 'medium',
  issuer: null,
  holderName: null,
  pageCount: 1,
  globalConfidence: null,
  reviewRequired: false,
  createdAt: '2026-01-01T00:00:00.000Z',
  updatedAt: '2026-01-01T00:00:00.000Z',
  processedAt: null,
  assumptions: [],
  issues: [],
  extractedFields: [],
  documentPages: [],
  reviewSessions: [],
  latestJob: null,
    processingMetadata: {
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
    processingTrace: []
  },
  lastReviewedAt: null,
  reportSections: [],
  humanSummary: null,
  reportHtml: null
}

test('resolveTenantProcessingOptions falls back to defaults', () => {
  process.env.OCR_DEFAULT_DECISION_PROFILE = 'aggressive'
  delete process.env.OCR_DEFAULT_VISUAL_ENGINE
  delete process.env.OCR_DEFAULT_STRUCTURED_MODE
  delete process.env.OCR_DEFAULT_ENSEMBLE_MODE
  delete process.env.OCR_DEFAULT_ENSEMBLE_ENGINES
  delete process.env.OCR_DEFAULT_FIELD_ADJUDICATION_MODE
  delete process.env.OCR_TENANT_PROCESSING_CONFIG
  const resolved = resolveTenantProcessingOptions(document)
  assert.equal(resolved.decisionProfile, 'aggressive')
  assert.equal(resolved.visualEngine, 'auto')
  assert.equal(resolved.structuredMode, 'auto')
  assert.equal(resolved.ensembleMode, 'always')
  assert.equal(resolved.ensembleEngines, 'rapidocr,google-documentai')
  assert.equal(resolved.fieldAdjudicationMode, 'auto')
})

test('resolveTenantProcessingOptions matches tenant-specific rules', () => {
  process.env.OCR_TENANT_PROCESSING_CONFIG = JSON.stringify({
    defaults: { decisionProfile: 'balanced' },
    rules: [{ tenantId: 'tenant-a', family: 'identity', visualEngine: 'paddleocr', decisionProfile: 'strict', structuredMode: 'openai' }]
  })
  const resolved = resolveTenantProcessingOptions(document)
  assert.equal(resolved.visualEngine, 'paddleocr')
  assert.equal(resolved.decisionProfile, 'strict')
  assert.equal(resolved.structuredMode, 'openai')
  delete process.env.OCR_TENANT_PROCESSING_CONFIG
})
