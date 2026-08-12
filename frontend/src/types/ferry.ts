/**
 * M5 / M7 L6 待引渡与社交引渡类型。
 */
import type { CharacterPublic } from './character'

/** 道友/同门引渡成本摘要（救援者支付） */
export interface SocialRescueCosts {
  same_region_stub?: boolean
  friend_cost: number
  sect_cost: number
  self_rescue_cost: number
  friend_cheaper_by?: number
  sect_cheaper_by?: number
  payer_label_zh?: string
}

/** GET /ferry/me */
export interface FerryPublic {
  deadline_at: string
  can_self_rescue: boolean
  /** 不可自救时的说明（灵石不足 / 冷却中等） */
  self_rescue_reason?: string | null
  /** 自救消耗数量 */
  self_rescue_cost?: number
  /** 消耗货币 id，如 spirit_stones */
  self_rescue_cost_currency?: string
  /** 消耗货币展示名，如「灵石」 */
  self_rescue_cost_label?: string
  /** 自救冷却剩余秒 */
  self_rescue_cooldown_seconds?: number
  /** 配置的冷却总秒数 */
  self_rescue_cooldown_total_seconds?: number
  /** 当前灵石（便于对照消耗） */
  spirit_stones?: number
  remaining_seconds?: number
  message?: string
  /** M7 L6：与自救对照的社交引渡成本 */
  social_rescue?: SocialRescueCosts
}

/** POST /ferry/rescue */
export interface FerryRescueRequest {
  mode: 'friend' | 'sect'
  target_character_id?: number | null
  target_name?: string | null
}

/** 自救 / 进入轮回 / 社交引渡 响应 */
export interface FerryMutationResult {
  character: CharacterPublic
  ferry?: FerryPublic | null
  message?: string
  /** 进入轮回后的预览/结果提示 */
  reincarnated?: boolean
  rescued?: boolean
  mode?: string
  mode_label_zh?: string
  spirit_stones_spent?: number
  victim_name?: string
  victim_character?: CharacterPublic
}
