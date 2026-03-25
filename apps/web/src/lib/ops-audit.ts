import { mkdir, readFile, writeFile } from 'fs/promises'
import path from 'path'

import { getSupabaseServerClient, hasSupabaseServerConfig } from '@/lib/supabase/server'

export type OpsAuditRecord = {
  id: string
  action: string
  tenantId: string | null
  documentId: string | null
  payload: Record<string, unknown>
  createdAt: string
}

const dataDirectory = path.join(process.cwd(), '.data')
const auditFile = path.join(dataDirectory, 'ops-audit.json')

function nowIso() {
  return new Date().toISOString()
}

function maybeUuid(value: string | null | undefined) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value ?? '') ? value : null
}

async function ensureLocalStore() {
  await mkdir(dataDirectory, { recursive: true })
  try {
    await readFile(auditFile, 'utf-8')
  } catch {
    await writeFile(auditFile, '[]', 'utf-8')
  }
}

async function readLocalAuditRecords() {
  await ensureLocalStore()
  const contents = await readFile(auditFile, 'utf-8')
  return JSON.parse(contents) as OpsAuditRecord[]
}

async function writeLocalAuditRecords(records: OpsAuditRecord[]) {
  await ensureLocalStore()
  await writeFile(auditFile, JSON.stringify(records, null, 2), 'utf-8')
}

export async function recordOpsAuditEvent(input: {
  action: string
  tenantId?: string | null
  documentId?: string | null
  payload?: Record<string, unknown>
}) {
  const record: OpsAuditRecord = {
    id: crypto.randomUUID(),
    action: input.action,
    tenantId: input.tenantId ?? null,
    documentId: input.documentId ?? null,
    payload: input.payload ?? {},
    createdAt: nowIso(),
  }

  if (hasSupabaseServerConfig()) {
    const supabase = getSupabaseServerClient()
    const write = await supabase.from('audit_logs').insert({
      id: record.id,
      tenant_id: maybeUuid(record.tenantId),
      document_id: maybeUuid(record.documentId),
      action: record.action,
      payload: {
        ...record.payload,
        tenantId: record.tenantId,
        documentId: record.documentId,
      },
      created_at: record.createdAt,
    })

    if (write.error) {
      throw new Error(write.error.message)
    }

    return record
  }

  const records = await readLocalAuditRecords()
  records.unshift(record)
  await writeLocalAuditRecords(records.slice(0, 5000))
  return record
}

export async function listOpsAuditEvents(options?: { actionPrefix?: string; documentId?: string | null; limit?: number }) {
  const limit = Math.max(1, options?.limit ?? 100)

  if (hasSupabaseServerConfig()) {
    const supabase = getSupabaseServerClient()
    let query = supabase.from('audit_logs').select('*').order('created_at', { ascending: false }).limit(limit)
    if (options?.actionPrefix) {
      query = query.ilike('action', `${options.actionPrefix}%`)
    }
    if (options?.documentId && maybeUuid(options.documentId)) {
      query = query.eq('document_id', options.documentId)
    }
    const result = await query
    if (result.error) {
      throw new Error(result.error.message)
    }
    return (result.data ?? []).map((row) => ({
      id: row.id,
      action: row.action,
      tenantId: (row.payload?.tenantId as string | undefined) ?? null,
      documentId: (row.payload?.documentId as string | undefined) ?? null,
      payload: (row.payload ?? {}) as Record<string, unknown>,
      createdAt: row.created_at,
    })) satisfies OpsAuditRecord[]
  }

  const records = await readLocalAuditRecords()
  return records
    .filter((record) => (options?.actionPrefix ? record.action.startsWith(options.actionPrefix) : true))
    .filter((record) => (options?.documentId ? record.documentId === options.documentId : true))
    .slice(0, limit)
}
