const webUrl = process.env.SMOKE_WEB_URL || 'http://127.0.0.1:3000'
const ocrApiUrl = process.env.SMOKE_OCR_API_URL || process.env.OCR_API_URL || 'http://127.0.0.1:8000'
const includeOps = process.env.SMOKE_INCLUDE_OPS === '1'

async function check(url, expectedField) {
  const response = await fetch(url, { cache: 'no-store' })
  if (!response.ok) {
    throw new Error(`${url} returned ${response.status}`)
  }
  const payload = await response.json()
  if (payload.status !== 'ok') {
    throw new Error(`${url} did not report ok status`)
  }
  if (expectedField && !(expectedField in payload)) {
    throw new Error(`${url} missing expected field ${expectedField}`)
  }
  return payload
}

async function checkJson(url, expectedField) {
  const response = await fetch(url, { cache: 'no-store' })
  if (!response.ok) {
    throw new Error(`${url} returned ${response.status}`)
  }
  const payload = await response.json()
  if (expectedField && !(expectedField in payload)) {
    throw new Error(`${url} missing expected field ${expectedField}`)
  }
  return payload
}

const webHealth = await check(`${webUrl}/api/health`, 'ocrApi')
const apiHealth = await check(`${ocrApiUrl}/v1/health`, 'ocr_runtime')

let ops = null
if (includeOps) {
  const learningLoop = await checkJson(`${webUrl}/api/datasets/learning-loop`, 'snapshot')
  const datasetRegistry = await checkJson(`${webUrl}/api/datasets/registry`, 'datasets')
  const routing = await checkJson(`${webUrl}/api/benchmarks/routing?limit=1`, 'results')
  const policyRecommendation = await checkJson(`${webUrl}/api/ops/calibration/recommendation`, 'recommendation')
  ops = { learningLoop, datasetRegistry, routing, policyRecommendation }
}

console.log(JSON.stringify({ webHealth, apiHealth, ops }, null, 2))
