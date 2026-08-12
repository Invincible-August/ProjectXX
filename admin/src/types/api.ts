/** 统一 API 信封。 */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T | null
}

/** 后台用户摘要。 */
export interface AdminUserInfo {
  id: number
  username: string
  display_name: string
  roles: string[]
}

/** 内容域清单项。 */
export interface DomainSummary {
  domain_id: string
  title: string
  filename: string
  risk: string
  description: string
  enabled: boolean
  category_id?: string
  category_title_zh?: string
  category_order?: number
  published_version: number
  has_published_overlay: boolean
  edit_modes?: string[]
  supports_sheets?: boolean
  supports_entries?: boolean
}

/** 字段中文说明。 */
export interface FieldMeta {
  key: string
  label_zh: string
  help_zh: string
  value_type: string
}

/** 运营表格（含行数据）。 */
export interface SheetView {
  sheet_id: string
  title_zh: string
  description_zh: string
  columns: FieldMeta[]
  primary_keys: string[]
  rows: Record<string, unknown>[]
}

/** 域编辑契约。 */
export interface DomainEditSchema {
  domain_id: string
  title_zh: string
  description_zh: string
  edit_modes: string[]
  fields: FieldMeta[]
  sheets: Array<Omit<SheetView, 'rows'>>
  entry_path: string[] | null
  entry_fields: FieldMeta[]
  dual_write_rule: string
  field_catalog?: FieldCatalogRow[]
  field_coverage?: {
    total_paths: number
    documented_paths: number
    undocumented_paths: number
    coverage_ratio: number
  }
  supports_sheets?: boolean
  supports_entries?: boolean
}

/** 全路径字段中文目录行。 */
export interface FieldCatalogRow {
  path: string
  label_zh: string
  help_zh: string
  value_kind: string
  documented: boolean
  sample: unknown
}

/** 审计日志行。 */
export interface AuditLogRow {
  id: number
  admin_user_id: number | null
  username: string
  action: string
  domain_id: string | null
  summary: string
  created_at: string | null
}
