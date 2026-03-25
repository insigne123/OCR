import test from 'node:test'
import assert from 'node:assert/strict'

import type { DocumentRecord } from '@ocr/shared'
import { redactDocumentForExternalSharing } from '../src/lib/pii.ts'

const sampleDocument: DocumentRecord = {
  id: 'doc-2',
  tenantId: 'tenant-1',
  filename: 'sensitive.pdf',
  mimeType: 'application/pdf',
  size: 100,
  storagePath: 'uploads/sensitive.pdf',
  storageProvider: 'local',
  sourceHash: 'hash',
  status: 'completed',
  decision: 'auto_accept',
  documentFamily: 'identity',
  country: 'CL',
  variant: 'identity-cl-front-text',
  riskLevel: 'medium',
  issuer: 'Registro Civil',
  holderName: 'JUAN PEREZ',
  pageCount: 1,
  globalConfidence: 0.95,
  reviewRequired: false,
  createdAt: '2026-01-01T00:00:00.000Z',
  updatedAt: '2026-01-01T00:00:00.000Z',
  processedAt: '2026-01-01T00:00:00.000Z',
  assumptions: [],
  issues: [],
  extractedFields: [
    {
      id: 'field-run',
      section: 'identity',
      fieldName: 'run',
      label: 'RUN',
      rawText: '12.345.678-5',
      normalizedValue: '12.345.678-5',
      valueType: 'text',
      confidence: 0.99,
      engine: 'heuristic',
      pageNumber: 1,
      bbox: null,
      evidenceSpan: { text: 'RUN: 12.345.678-5', start: null, end: null },
      validationStatus: 'valid',
      reviewStatus: 'confirmed',
      isInferred: false,
      issueIds: [],
      candidates: [
        {
          engine: 'google-documentai',
          source: 'google-documentai',
          value: '12.345.678-5',
          rawText: 'RUN: 12.345.678-5',
          confidence: 0.99,
          pageNumber: 1,
          bbox: null,
          evidenceText: 'RUN: 12.345.678-5',
          selected: true,
          matchType: 'layout-pair',
          score: 0.99
        }
      ],
      consensus: {
        enginesConsidered: 1,
        candidateCount: 1,
        supportingEngines: ['google-documentai'],
        agreementRatio: 1,
        disagreement: false
      },
      adjudication: {
        method: 'deterministic',
        abstained: false,
        selectedValue: '12.345.678-5',
        selectedSource: 'google-documentai',
        selectedEngine: 'google-documentai',
        confidence: 0.99,
        rationale: 'Best supported value.',
        evidenceSources: ['google-documentai']
      }
    }
  ],
  documentPages: [],
  reviewSessions: [],
  latestJob: null,
  processingMetadata: {
    packId: 'identity-cl-front',
    packVersion: '2026-03',
    documentSide: 'front',
    crossSideDetected: false,
    decisionProfile: 'balanced',
    requestedVisualEngine: 'auto',
    selectedVisualEngine: 'google-documentai',
    ensembleMode: 'ensemble',
    classificationConfidence: 0.95,
    extractionSource: 'plain-text',
    processingEngine: 'heuristic-text',
    ocrRuns: [
      {
        engine: 'google-documentai',
        source: 'google-documentai',
        success: true,
        selected: true,
        score: 0.98,
        pageCount: 1,
        text: 'RUN 12.345.678-5 JUAN PEREZ',
        averageConfidence: 0.98,
        classificationFamily: 'identity',
        classificationCountry: 'CL',
        classificationConfidence: 0.95,
        supportedClassification: true,
        assumptions: [],
        pages: [{ pageNumber: 1, text: 'RUN 12.345.678-5 JUAN PEREZ', tokenCount: 4, averageConfidence: 0.98 }],
        tokens: [],
        keyValuePairs: [],
        tableCandidateRows: []
      }
    ],
    adjudicationMode: 'deterministic',
    adjudicatedFields: 1,
    adjudicationAbstentions: 0,
    processingTrace: []
  },
  lastReviewedAt: null,
  reportSections: [],
  humanSummary: null,
  reportHtml: null
}

test('redactDocumentForExternalSharing masks holder names and identifiers', () => {
  const redacted = redactDocumentForExternalSharing(sampleDocument)
  assert.notEqual(redacted.holderName, sampleDocument.holderName)
  assert.notEqual(redacted.extractedFields[0].normalizedValue, sampleDocument.extractedFields[0].normalizedValue)
  assert.match(redacted.extractedFields[0].normalizedValue ?? '', /\*+/)
  assert.match(redacted.extractedFields[0].candidates[0].value ?? '', /\*+/)
  assert.equal(redacted.processingMetadata.ocrRuns[0].text, '[REDACTED]')
})
