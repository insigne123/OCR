export type WebFeatureFlags = {
  adaptiveRouting: boolean
  reviewAttentionQueue: boolean
  jobsDlqRequeue: boolean
}

const DEFAULT_FLAGS: WebFeatureFlags = {
  adaptiveRouting: true,
  reviewAttentionQueue: true,
  jobsDlqRequeue: true,
}

let cachedFlags: WebFeatureFlags | null = null

function coerceBoolean(value: unknown) {
  if (typeof value === 'boolean') return value
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase()
    if (['1', 'true', 'yes', 'on', 'enabled'].includes(normalized)) return true
    if (['0', 'false', 'no', 'off', 'disabled'].includes(normalized)) return false
  }
  return null
}

function parseRuntimeFlags(): Partial<WebFeatureFlags> {
  const raw = process.env.NEXT_PUBLIC_OCR_WEB_FEATURE_FLAGS ?? process.env.OCR_WEB_FEATURE_FLAGS
  if (!raw) return {}

  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>
    const overrides: Partial<WebFeatureFlags> = {}
    const adaptiveRouting = coerceBoolean(parsed.adaptiveRouting)
    const reviewAttentionQueue = coerceBoolean(parsed.reviewAttentionQueue)
    const jobsDlqRequeue = coerceBoolean(parsed.jobsDlqRequeue)
    if (adaptiveRouting != null) overrides.adaptiveRouting = adaptiveRouting
    if (reviewAttentionQueue != null) overrides.reviewAttentionQueue = reviewAttentionQueue
    if (jobsDlqRequeue != null) overrides.jobsDlqRequeue = jobsDlqRequeue
    return overrides
  } catch {
    return {}
  }
}

export function getWebFeatureFlags(): WebFeatureFlags {
  if (cachedFlags) return cachedFlags
  cachedFlags = {
    ...DEFAULT_FLAGS,
    ...parseRuntimeFlags(),
  }
  return cachedFlags
}

export function isWebFeatureEnabled(name: keyof WebFeatureFlags) {
  return getWebFeatureFlags()[name]
}

export function resetWebFeatureFlagsForTests() {
  cachedFlags = null
}
