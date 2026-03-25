import { readFile } from 'fs/promises'
import path from 'path'

import { ensureRouteAccessJson } from '@/lib/route-auth'

const registryPath = path.join(process.cwd(), '.data', 'dataset-registry.json')

export async function GET(_: Request, context: { params: Promise<{ name: string }> }) {
  const unauthorized = await ensureRouteAccessJson()
  if (unauthorized) return unauthorized

  const { name } = await context.params
  let registry: Array<Record<string, unknown>> = []
  try {
    registry = JSON.parse(await readFile(registryPath, 'utf-8')) as Array<Record<string, unknown>>
  } catch {
    return Response.json({ error: 'Dataset registry not found' }, { status: 404 })
  }
  const dataset = registry.find((entry) => entry.name === name)
  if (!dataset) {
    return Response.json({ error: 'Dataset not found' }, { status: 404 })
  }

  const manifestPath = path.isAbsolute(String(dataset.manifest)) ? String(dataset.manifest) : path.join(process.cwd(), String(dataset.manifest))
  const entries = (await readFile(manifestPath, 'utf-8'))
    .split('\n')
    .filter(Boolean)
    .map((line) => JSON.parse(line) as Record<string, unknown>)

  return Response.json({
    dataset,
    summary: {
      documents: entries.length,
      captureConditions: [...new Set(entries.map((entry) => String(entry.capture_condition ?? 'unknown')))].sort(),
      splits: [...new Set(entries.map((entry) => String(entry.split ?? 'unspecified')))].sort(),
      benchmarkProfiles: [...new Set(entries.map((entry) => String(entry.benchmark_profile ?? 'unspecified')))].sort(),
    },
    sample: entries.slice(0, 10),
  })
}
