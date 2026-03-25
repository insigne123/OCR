import test from 'node:test'
import assert from 'node:assert/strict'

import type { DocumentRecord } from '@ocr/shared'
import {
  buildActiveLearningQueue,
  buildCalibrationInsights,
  buildGoldenSet,
  buildLearningLoopSnapshot,
  buildReviewedDatasetExamples,
  evaluateGoldenSet,
} from '../src/lib/training-dataset.ts'

const baseDocument: DocumentRecord = {
  id: 'doc-1',
  tenantId: 'tenant-1',
  filename: 'demo.pdf',
  mimeType: 'application/pdf',
  size: 100,
  storagePath: 'uploads/demo.pdf',
  storageProvider: 'local',
  sourceHash: 'hash',
  status: 'completed',
  decision: 'accept_with_warning',
  documentFamily: 'certificate',
  country: 'CL',
  variant: 'certificate-cl-previsional-text',
  riskLevel: 'medium',
  issuer: 'AFP ProVida',
  holderName: 'JUAN PEREZ',
  pageCount: 1,
  globalConfidence: 0.91,
  reviewRequired: false,
  createdAt: '2026-01-01T00:00:00.000Z',
  updatedAt: '2026-01-01T00:00:00.000Z',
  processedAt: '2026-01-01T00:00:00.000Z',
  assumptions: ['demo'],
  issues: [],
  extractedFields: [
    {
      id: 'field-rut',
      section: 'identifiers',
      fieldName: 'rut',
      label: 'RUT',
      rawText: '12.345.678-5',
      normalizedValue: '12.345.678-5',
      valueType: 'text',
      confidence: 0.99,
      engine: 'heuristic',
      pageNumber: 1,
      bbox: null,
      evidenceSpan: { text: 'RUT: 12.345.678-5', start: null, end: null },
      validationStatus: 'valid',
      reviewStatus: 'corrected',
      isInferred: false,
      issueIds: [],
      candidates: [],
      consensus: null,
      adjudication: null
    }
  ],
  documentPages: [],
  reviewSessions: [
    {
      id: 'session-1',
      reviewerName: 'Analista OCR',
      status: 'completed',
      notes: null,
      openedAt: '2026-01-01T00:00:00.000Z',
      updatedAt: '2026-01-01T00:00:00.000Z',
      edits: [
        {
          id: 'edit-1',
          fieldId: 'field-rut',
          fieldName: 'rut',
          previousValue: '12.345.678-K',
          newValue: '12.345.678-5',
          reason: 'Correccion manual',
          createdAt: '2026-01-01T00:00:00.000Z',
          reviewerName: 'Analista OCR'
        }
      ]
    }
  ],
  latestJob: null,
  processingMetadata: {
    packId: 'certificate-cl-previsional',
    packVersion: '2026-03',
    documentSide: null,
    crossSideDetected: false,
    decisionProfile: 'balanced',
    requestedVisualEngine: 'auto',
    selectedVisualEngine: 'google-documentai',
    ensembleMode: 'ensemble',
    classificationConfidence: 0.95,
    extractionSource: 'plain-text',
    processingEngine: 'heuristic-text',
    ocrRuns: [],
    adjudicationMode: null,
    adjudicatedFields: 0,
    adjudicationAbstentions: 0,
    processingTrace: []
  },
  lastReviewedAt: '2026-01-01T00:00:00.000Z',
  reportSections: [],
  humanSummary: null,
  reportHtml: null
}

const riskyDocument: DocumentRecord = {
  ...baseDocument,
  id: 'doc-2',
  filename: 'identity-front.pdf',
  decision: 'auto_accept',
  documentFamily: 'identity',
  variant: 'identity-cl-front-text',
  globalConfidence: 0.82,
  extractedFields: [
    {
      id: 'field-doc-number',
      section: 'identity',
      fieldName: 'document_number',
      label: 'Numero de documento',
      rawText: '12.345.678-K',
      normalizedValue: '12.345.678-5',
      valueType: 'text',
      confidence: 0.73,
      engine: 'ocr-api',
      pageNumber: 1,
      bbox: null,
      evidenceSpan: { text: '12.345.678-K', start: null, end: null },
      validationStatus: 'warning',
      reviewStatus: 'corrected',
      isInferred: false,
      issueIds: ['issue-1'],
      candidates: [],
      consensus: {
        enginesConsidered: 3,
        candidateCount: 2,
        supportingEngines: ['google-documentai'],
        agreementRatio: 0.33,
        disagreement: true,
      },
      adjudication: {
        method: 'deterministic',
        abstained: true,
        selectedValue: null,
        selectedSource: null,
        selectedEngine: null,
        confidence: 0.62,
        rationale: 'Conflicting evidence.',
        evidenceSources: ['google-documentai', 'azure-document-intelligence'],
      },
    },
  ],
  reviewSessions: [
    {
      id: 'session-2',
      reviewerName: 'Analista OCR',
      status: 'completed',
      notes: null,
      openedAt: '2026-01-02T00:00:00.000Z',
      updatedAt: '2026-01-02T00:00:00.000Z',
      edits: [
        {
          id: 'edit-2',
          fieldId: 'field-doc-number',
          fieldName: 'document_number',
          previousValue: '12.345.678-K',
          newValue: '12.345.678-5',
          reason: 'OCR disagreement',
          createdAt: '2026-01-02T00:00:00.000Z',
          reviewerName: 'Analista OCR',
        },
      ],
    },
  ],
  processingMetadata: {
    ...baseDocument.processingMetadata,
    packId: 'identity-cl-front',
    adjudicationMode: 'deterministic',
    adjudicatedFields: 0,
    adjudicationAbstentions: 1,
    processingTrace: [],
  },
  lastReviewedAt: '2026-01-02T00:00:00.000Z',
}

test('buildReviewedDatasetExamples returns reviewed examples', () => {
  const examples = buildReviewedDatasetExamples([baseDocument])
  assert.equal(examples.length, 1)
  assert.equal(examples[0].target.fields.rut, '12.345.678-5')
  assert.equal(examples[0].target.edits[0].previousValue, '12.345.678-K')
})

test('evaluateGoldenSet computes exact matches', () => {
  const goldenSet = buildGoldenSet([baseDocument])
  const evaluation = evaluateGoldenSet([baseDocument], goldenSet)
  assert.equal(evaluation.totalDocuments, 1)
  assert.equal(evaluation.exactMatchRate, 1)
  assert.equal(evaluation.perDocument[0].mismatches.length, 0)
})

test('buildActiveLearningQueue prioritizes corrected auto-accept disagreements', () => {
  const queue = buildActiveLearningQueue([baseDocument, riskyDocument])
  assert.equal(queue[0].documentId, 'doc-2')
  assert.equal(queue[0].signals.falseAcceptRisk, true)
  assert.ok(queue[0].priorityScore > queue[1].priorityScore)
})

test('buildCalibrationInsights recommends tightening for false accepts', () => {
  const calibrationDocuments = [
    ...Array.from({ length: 5 }, (_, index) => ({
      ...riskyDocument,
      id: `risky-${index}`,
      filename: `risky-${index}.pdf`,
    })),
  ]

  const insights = buildCalibrationInsights(calibrationDocuments)
  assert.equal(insights[0].packId, 'identity-cl-front')
  assert.equal(insights[0].recommendation, 'tighten_auto_accept')
  assert.equal(insights[0].falseAcceptCorrections, 5)
  assert.ok(insights[0].suggestedAdjustments.autoAcceptConfidenceDelta > 0)
})

test('buildLearningLoopSnapshot reports queue and pack totals', () => {
  const snapshot = buildLearningLoopSnapshot([baseDocument, riskyDocument], { limit: 10 })
  assert.equal(snapshot.totals.reviewedDocuments, 2)
  assert.equal(snapshot.totals.queueSize, 2)
  assert.equal(snapshot.totals.packsTracked, 2)
  assert.equal(snapshot.totals.falseAcceptCorrections, 1)
})
