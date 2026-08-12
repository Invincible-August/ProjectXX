/**
 * 突破 API 类型（M1 + M5-D05 真读条）。
 */
import type { CharacterPublic } from './character'

/** GET /breakthrough/preview */
export interface BreakthroughPreview {
  can_attempt: boolean
  reason: string
  required_cultivation: number
  current_cultivation: number
  spirit_stone_cost: number
  success_rate: number
  advance_type: 'layer' | 'major' | null
  /** 进阶方式中文，如「同境升层/升期」 */
  advance_type_label_zh?: string | null
  next_realm_display: string | null
  /** 跨境时可选品阶说明 */
  grade_preview?: string | null
  /** 是否启用服务端真读条 */
  async_channel_enabled?: boolean
  async_channel_label_zh?: string
  async_channel_hint_zh?: string
  client_poll_ms?: number
  /** 进行中读条；无则 null */
  channel?: BreakthroughChannel | null
  just_resolved?: boolean
  resolved_result?: BreakthroughAttemptResult
}

/** 服务端修为区间骰出目（只展示，禁止客户端自掷成败） */
export interface BreakthroughDiceBlock {
  roll: number
  threshold: number
  lo: number
  hi: number
  base_min?: number
  base_max?: number
  success_rate?: number
}

/** 真读条进度信封（权威 ends_at；前端只做展示插值） */
export interface BreakthroughChannel {
  state: 'in_progress' | 'resolved'
  session_id?: number
  progress_ratio: number
  started_at: string
  ends_at: string
  remaining_seconds: number
  duration_seconds: number
  advance_type: 'layer' | 'major' | string
  advance_type_label_zh: string
  label_zh?: string
  hint_zh?: string
  client_poll_ms?: number
  result?: BreakthroughAttemptResult
}

/** POST /breakthrough/attempt 或 channel 结算结果 */
export interface BreakthroughAttemptResult {
  success: boolean | null
  advance_type: 'layer' | 'major'
  message: string
  cultivation_delta: number
  spirit_stones_delta: number
  character: CharacterPublic
  grade?: string | null
  grade_name?: string | null
  divine_ability_slots?: number
  /** 服务端骰子块；失败/成功均可能带回 */
  dice?: BreakthroughDiceBlock | null
  /**
   * M5：需进入雷劫渡劫流程时为 true。
   * 此时通常不直接进阶，前端应 start-prep 并跳转 /tribulation。
   */
  needs_tribulation?: boolean
  /** 真读条已开始（尚未揭晓成败） */
  channel_started?: boolean
  channel?: BreakthroughChannel | null
  channel_resolved?: boolean
}

/** GET /breakthrough/channel */
export interface BreakthroughChannelResponse {
  channel: BreakthroughChannel | null
  character: CharacterPublic
  just_resolved?: boolean
}

/** GET /breakthrough/grades/history */
export interface GradeHistoryItem {
  from_realm_display: string
  to_realm_display: string
  grade: string
  grade_name?: string
  created_at: string
}
