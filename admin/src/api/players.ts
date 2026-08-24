/** 玩家账号管理 API：列表 / 封号 / 软删 / GM / 重置密码 / 改联系方式 / 派发仙缘 / 打赏与广告流水。 */
import { http, unwrap } from './http'

export interface FieldMetaDto {
  key: string
  label_zh: string
  help_zh: string
  value_type: string
}

export interface SheetMetaDto {
  sheet_id: string
  title_zh: string
  description_zh: string
  columns: FieldMetaDto[]
  primary_keys: string[]
}

export interface PlayerOpsSchema {
  module_id: string
  title_zh: string
  description_zh: string
  page_sizes: number[]
  default_page_size: number
  tip_channel_presets: string[]
  reset_password_plaintext: string
  forms: {
    tip_create: FieldMetaDto[]
    grant_fate_luck: FieldMetaDto[]
    contacts: FieldMetaDto[]
  }
  sheets: SheetMetaDto[]
  note_zh: string
}

export interface PlayerAccountRow {
  /** 数据库自增主键；运营 API 路径使用此 id */
  id: number
  /** 对外账号号 M/P/T/G + 7 位 */
  user_id: string
  email: string | null
  phone: string | null
  is_active: boolean
  is_banned: boolean
  is_gm: boolean
  fate_luck: number
  total_recharge_amount: number
  character_id: number | null
  character_name: string | null
  created_at: string | null
}

export interface PlayerAccountListResult {
  items: PlayerAccountRow[]
  total: number
  page: number
  page_size: number
}

export interface TipRecordRow {
  id: number
  user_id: number
  paid_at: string | null
  channel: string
  order_no: string
  amount: number
  note: string | null
  created_by_admin_name: string | null
  created_at: string | null
}

export interface FateLuckGrantRow {
  id: number
  user_id: number
  character_id: number | null
  granted_at: string | null
  amount: number
  before_amount: number
  after_amount: number
  note: string | null
  created_by_admin_name: string | null
  created_at: string | null
}

export interface AdWatchRow {
  id: number
  user_id: number
  watched_at: string | null
  platform: string
  ad_unit: string | null
  created_at: string | null
}

export interface PagedResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  user_id: number
  watch_count?: number
}

export async function fetchPlayerOpsSchema() {
  return unwrap<PlayerOpsSchema>(http.get('/ops/players/schema'))
}

export async function fetchPlayerAccounts(params: {
  q?: string
  page?: number
  page_size?: number
}) {
  return unwrap<PlayerAccountListResult>(
    http.get('/ops/players', {
      params: {
        q: params.q || undefined,
        page: params.page ?? 1,
        page_size: params.page_size ?? 20,
      },
    }),
  )
}

export async function banPlayer(dbId: number, banned: boolean, note?: string) {
  return unwrap<PlayerAccountRow>(
    http.post(`/ops/players/${dbId}/ban`, { banned, note: note || null }),
  )
}

export async function softDeletePlayer(dbId: number, note?: string) {
  return unwrap<PlayerAccountRow>(
    http.post(`/ops/players/${dbId}/soft-delete`, { note: note || null }),
  )
}

export async function setPlayerGm(dbId: number, isGm: boolean, note?: string) {
  return unwrap<PlayerAccountRow>(
    http.post(`/ops/players/${dbId}/set-gm`, { is_gm: isGm, note: note || null }),
  )
}

export async function resetPlayerPassword(dbId: number, note?: string) {
  return unwrap<PlayerAccountRow & { message?: string }>(
    http.post(`/ops/players/${dbId}/reset-password`, { note: note || null }),
  )
}

export async function updatePlayerContacts(
  dbId: number,
  body: { email?: string | null; phone?: string | null; note?: string },
) {
  return unwrap<PlayerAccountRow>(http.post(`/ops/players/${dbId}/contacts`, body))
}

export async function grantPlayerFateLuck(dbId: number, amount: number, note?: string) {
  return unwrap<PlayerAccountRow>(
    http.post(`/ops/players/${dbId}/grant-fate-luck`, { amount, note: note || null }),
  )
}

export async function createPlayerTip(
  dbId: number,
  body: {
    paid_at: string
    channel: string
    order_no: string
    amount: number
    note?: string
  },
) {
  return unwrap<{ account: PlayerAccountRow; tip: TipRecordRow }>(
    http.post(`/ops/players/${dbId}/tips`, body),
  )
}

export async function fetchPlayerTips(
  dbId: number,
  params?: { page?: number; page_size?: number },
) {
  return unwrap<PagedResult<TipRecordRow>>(
    http.get(`/ops/players/${dbId}/tips`, {
      params: { page: params?.page ?? 1, page_size: params?.page_size ?? 20 },
    }),
  )
}

export async function fetchFateLuckGrants(
  dbId: number,
  params?: { page?: number; page_size?: number },
) {
  return unwrap<PagedResult<FateLuckGrantRow>>(
    http.get(`/ops/players/${dbId}/fate-luck-grants`, {
      params: { page: params?.page ?? 1, page_size: params?.page_size ?? 20 },
    }),
  )
}

export async function fetchAdWatches(
  dbId: number,
  params?: { page?: number; page_size?: number },
) {
  return unwrap<PagedResult<AdWatchRow>>(
    http.get(`/ops/players/${dbId}/ad-watches`, {
      params: { page: params?.page ?? 1, page_size: params?.page_size ?? 20 },
    }),
  )
}
