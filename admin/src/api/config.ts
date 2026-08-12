/** 配置域 / 审计 / 导入导出 / 条目表 API。 */
import { http, unwrap } from './http'
import type { AuditLogRow, DomainSummary } from '../types/api'

export async function fetchDomains() {
  return unwrap<{ domains: DomainSummary[] }>(http.get('/config/domains'))
}

export async function fetchBundleSummary() {
  return unwrap<Record<string, unknown>>(http.get('/config/bundle/summary'))
}

export async function fetchEffective(domainId: string) {
  return unwrap<{
    domain_id: string
    payload: Record<string, unknown>
    yaml_base: Record<string, unknown>
  }>(http.get(`/config/${domainId}/effective`))
}

export async function fetchDraft(domainId: string) {
  return unwrap<{
    domain_id: string
    payload: Record<string, unknown>
    preview_effective: Record<string, unknown>
    updated_at: string | null
  }>(http.get(`/config/${domainId}/draft`))
}

export async function saveDraft(domainId: string, payload: Record<string, unknown>) {
  return unwrap(http.put(`/config/${domainId}/draft`, { payload }))
}

export async function validateDraft(domainId: string, payload: Record<string, unknown>) {
  return unwrap(http.post(`/config/${domainId}/validate`, { payload }))
}

export async function publishDomain(
  domainId: string,
  note: string,
  confirmHighRisk: boolean,
) {
  return unwrap(
    http.post(`/config/${domainId}/publish`, {
      note,
      confirm_high_risk: confirmHighRisk,
    }),
  )
}

export async function rollbackDomain(
  domainId: string,
  targetVersion: number | null,
  confirmHighRisk: boolean,
) {
  return unwrap(
    http.post(`/config/${domainId}/rollback`, {
      target_version: targetVersion,
      confirm_high_risk: confirmHighRisk,
    }),
  )
}

export async function fetchRevisions(domainId: string) {
  return unwrap<{ revisions: Array<Record<string, unknown>> }>(
    http.get(`/config/${domainId}/revisions`),
  )
}

export async function fetchAuditLogs(domainId?: string) {
  return unwrap<{ logs: AuditLogRow[] }>(
    http.get('/audit/logs', { params: domainId ? { domain_id: domainId } : {} }),
  )
}

export async function exportDomain(
  domainId: string,
  source: 'effective' | 'yaml' | 'draft' = 'effective',
  format: 'json' | 'yaml' = 'json',
) {
  return unwrap<{ domain_id: string; source: string; format: string; content: string }>(
    http.get(`/config/${domainId}/export`, { params: { source, format } }),
  )
}

export async function importDomain(
  domainId: string,
  content: string,
  format: 'json' | 'yaml' = 'json',
  mode: 'merge' | 'replace' = 'merge',
) {
  return unwrap(
    http.post(`/config/${domainId}/import`, { content, format, mode }),
  )
}

export async function fetchEntries(domainId: string) {
  return unwrap<{
    domain_id: string
    path: string[]
    entries: Record<string, Record<string, unknown>>
    draft_entry_ids: string[]
  }>(http.get(`/config/${domainId}/entries`))
}

export async function upsertEntry(
  domainId: string,
  entryId: string,
  body: Record<string, unknown>,
) {
  return unwrap(http.put(`/config/${domainId}/entries/${encodeURIComponent(entryId)}`, { body }))
}

export async function deleteEntry(domainId: string, entryId: string) {
  return unwrap(http.delete(`/config/${domainId}/entries/${encodeURIComponent(entryId)}`))
}

export async function exportEntriesCsv(domainId: string) {
  return unwrap<{ domain_id: string; format: string; content: string }>(
    http.get(`/config/${domainId}/entries/export.csv`),
  )
}

export async function importEntriesCsv(
  domainId: string,
  content: string,
  mode: 'merge' | 'replace' = 'merge',
) {
  return unwrap(http.post(`/config/${domainId}/entries/import.csv`, { content, mode }))
}

export async function fetchDomainSchema(domainId: string) {
  return unwrap<import('../types/api').DomainEditSchema>(
    http.get(`/config/${domainId}/schema`),
  )
}

export async function fetchSheets(domainId: string) {
  return unwrap<{
    domain_id: string
    source: string
    sheets: import('../types/api').SheetView[]
    schema: import('../types/api').DomainEditSchema
  }>(http.get(`/config/${domainId}/sheets`))
}

export async function saveSheets(
  domainId: string,
  sheets: Array<{ sheet_id: string; rows: Record<string, unknown>[] }>,
  replaceDraft = true,
) {
  return unwrap(
    http.put(`/config/${domainId}/sheets`, {
      sheets,
      replace_draft: replaceDraft,
    }),
  )
}
