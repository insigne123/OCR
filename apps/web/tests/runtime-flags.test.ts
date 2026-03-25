import test from 'node:test'
import assert from 'node:assert/strict'

import { getWebFeatureFlags, isWebFeatureEnabled, resetWebFeatureFlagsForTests } from '../src/lib/runtime-flags.ts'

test('web runtime flags default to enabled operational features', () => {
  delete process.env.NEXT_PUBLIC_OCR_WEB_FEATURE_FLAGS
  delete process.env.OCR_WEB_FEATURE_FLAGS
  resetWebFeatureFlagsForTests()

  const flags = getWebFeatureFlags()
  assert.equal(flags.adaptiveRouting, true)
  assert.equal(flags.reviewAttentionQueue, true)
  assert.equal(flags.jobsDlqRequeue, true)
})

test('web runtime flags respect env overrides', () => {
  process.env.OCR_WEB_FEATURE_FLAGS = JSON.stringify({
    adaptiveRouting: false,
    jobsDlqRequeue: false,
  })
  resetWebFeatureFlagsForTests()

  assert.equal(isWebFeatureEnabled('adaptiveRouting'), false)
  assert.equal(isWebFeatureEnabled('jobsDlqRequeue'), false)
  assert.equal(isWebFeatureEnabled('reviewAttentionQueue'), true)

  delete process.env.OCR_WEB_FEATURE_FLAGS
  resetWebFeatureFlagsForTests()
})
