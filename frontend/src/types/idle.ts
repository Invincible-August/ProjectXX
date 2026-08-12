/**
 * 挂机 / 修炼 API 类型（M1 实时 + M2 三向 / 离线）。
 */
import type { CharacterPublic, OfflinePending } from './character'

/** POST /idle/direction | /idle/sync 响应 data */
export interface IdleSyncData {
  character: CharacterPublic
  settled_ticks: number
  gained_cultivation: number
  gained_body?: number
  gained_crafting?: number
  spent_spirit_stones: number
  /** 采矿个人灵石入账 */
  gained_mining_stones?: number
  /** 采矿扣体力 */
  spent_stamina?: number
  /** 采矿顺带宗门库入账 */
  mining_pool_stones?: number
  /** 下一片理论到期 ISO UTC；未修炼/停滞为 null */
  next_tick_at: string | null
}

export type IdleDirection = 'none' | 'spirit' | 'body' | 'crafting' | 'sect_mining'

/** GET /idle/offline/preview */
export interface OfflinePreviewData {
  has_pending: boolean
  pending: OfflinePending | null
  character: CharacterPublic
}

/** POST /idle/offline/claim */
export interface OfflineClaimData {
  applied: OfflinePending
  character: CharacterPublic
  next_tick_at?: string | null
}
