import { readFile } from 'fs/promises'
import path from 'path'

import { ensureRouteAccessJson } from '@/lib/route-auth'

const registryPath = path.join(process.cwd(), '.data', 'dataset-registry.json')

export async function GET() {
  const unauthorized = await ensureRouteAccessJson()
  if (unauthorized) return unauthorized

  try {
    const contents = await readFile(registryPath, 'utf-8')
    return Response.json({
      datasets: JSON.parse(contents),
    })
  } catch {
    return Response.json({ datasets: [] })
  }
}
