import fs from 'node:fs'
import path from 'node:path'

import { createClient } from '@supabase/supabase-js'

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return {}
  const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/)
  const values = {}
  for (const line of lines) {
    if (!line || line.trim().startsWith('#')) continue
    const index = line.indexOf('=')
    if (index === -1) continue
    const key = line.slice(0, index).trim()
    const rawValue = line.slice(index + 1).trim()
    values[key] = rawValue.replace(/^['"]|['"]$/g, '')
  }
  return values
}

function loadRuntimeEnv() {
  const cwd = process.cwd()
  return {
    ...loadEnvFile(path.join(cwd, '.env')),
    ...loadEnvFile(path.join(cwd, '.env.local')),
    ...process.env,
  }
}

const env = loadRuntimeEnv()
const url = env.NEXT_PUBLIC_SUPABASE_URL
const serviceRoleKey = env.SUPABASE_SERVICE_ROLE_KEY
const bucket = env.SUPABASE_STORAGE_BUCKET || 'documents'

if (!url || !serviceRoleKey) {
  console.log(JSON.stringify({ configured: false, reason: 'Missing Supabase env vars' }, null, 2))
  process.exit(0)
}

const client = createClient(url, serviceRoleKey, { auth: { persistSession: false } })

const buckets = await client.storage.listBuckets()
const health = {
  configured: true,
  reachable: !buckets.error,
  bucketConfigured: bucket,
  bucketExists: (buckets.data ?? []).some((item) => item.name === bucket),
}

if (buckets.error) {
  health.error = buckets.error.message
}

console.log(JSON.stringify(health, null, 2))
