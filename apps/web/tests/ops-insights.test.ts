import test from 'node:test'
import assert from 'node:assert/strict'

import { buildDecisionPolicyRecommendation, compareOperationalSnapshots } from '../src/lib/ops-insights.ts'

test('buildDecisionPolicyRecommendation generates threshold rules from calibration insights', () => {
  const recommendation = buildDecisionPolicyRecommendation([
    {
      packId: 'identity-cl-front',
      family: 'identity',
      country: 'CL',
      variant: 'identity-cl-front-text',
      documentCount: 10,
      reviewedDocuments: 8,
      correctedDocuments: 3,
      falseAcceptCorrections: 2,
      straightThroughRate: 0.7,
      reviewRate: 0.2,
      correctionRate: 0.25,
      averageConfidence: 0.9,
      averageAgreement: 0.82,
      disagreementRate: 0.18,
      adjudicationAbstentionRate: 0.1,
      recommendation: 'tighten_auto_accept',
      suggestedAdjustments: {
        autoAcceptConfidenceDelta: 0.02,
        autoAcceptAgreementDelta: 0.05,
        acceptWithWarningConfidenceDelta: 0.01,
      },
    },
  ])

  assert.equal(recommendation.summary.totalRules, 1)
  assert.equal(recommendation.config.rules[0].packId, 'identity-cl-front')
  assert.ok(recommendation.config.rules[0].thresholds.autoAcceptConfidence > 0.9)
})

test('compareOperationalSnapshots summarizes routing benchmark deltas', () => {
  const comparison = compareOperationalSnapshots(
    [
      {
        id: 'latest',
        action: 'snapshot.routing_benchmark',
        tenantId: null,
        documentId: null,
        createdAt: '2026-03-18T12:00:00.000Z',
        payload: {
          recommendedOverall: { strategy: 'local_google' },
          results: [
            { strategy: 'local_google', exactMatchRate: 0.98, straightThroughRate: 0.9, estimatedCostPerDocument: 0.05 },
            { strategy: 'ensemble_adjudicator', exactMatchRate: 0.99, straightThroughRate: 0.91, estimatedCostPerDocument: 0.1 },
          ],
        },
      },
      {
        id: 'previous',
        action: 'snapshot.routing_benchmark',
        tenantId: null,
        documentId: null,
        createdAt: '2026-03-17T12:00:00.000Z',
        payload: {
          recommendedOverall: { strategy: 'ensemble_adjudicator' },
          results: [
            { strategy: 'local_google', exactMatchRate: 0.95, straightThroughRate: 0.82, estimatedCostPerDocument: 0.05 },
            { strategy: 'ensemble_adjudicator', exactMatchRate: 0.985, straightThroughRate: 0.9, estimatedCostPerDocument: 0.1 },
          ],
        },
      },
    ],
    'snapshot.routing_benchmark'
  )

  assert.equal(comparison?.metrics.latestRecommendedStrategy, 'local_google')
  assert.equal(comparison?.metrics.previousRecommendedStrategy, 'ensemble_adjudicator')
  assert.equal(comparison?.metrics.bestImprovementStrategy, 'local_google')
})

test('compareOperationalSnapshots summarizes ocr cost deltas', () => {
  const comparison = compareOperationalSnapshots(
    [
      {
        id: 'latest-cost',
        action: 'snapshot.ocr_costs',
        tenantId: null,
        documentId: null,
        createdAt: '2026-03-18T12:00:00.000Z',
        payload: {
          totals: {
            estimatedCostPerDocument: 0.031,
            totalOpenaiFields: 3,
            premiumEscalationRate: 0.22,
          },
        },
      },
      {
        id: 'previous-cost',
        action: 'snapshot.ocr_costs',
        tenantId: null,
        documentId: null,
        createdAt: '2026-03-17T12:00:00.000Z',
        payload: {
          totals: {
            estimatedCostPerDocument: 0.042,
            totalOpenaiFields: 6,
            premiumEscalationRate: 0.35,
          },
        },
      },
    ],
    'snapshot.ocr_costs'
  )

  assert.equal(comparison?.metrics.latestEstimatedCostPerDocument, 0.031)
  assert.equal(comparison?.metrics.previousEstimatedCostPerDocument, 0.042)
  assert.equal(comparison?.metrics.totalOpenaiFieldsDelta, -3)
})
