/**
 * M7 L7 双修 / 四榜类型。
 */

export type DualGender = 'male' | 'female'

export interface DualTechnique {
  technique_id: string
  label: string
  mode: 'mutual_gain' | 'transfer'
  require_opposite_gender?: boolean
  base_yield?: number
  [key: string]: unknown
}

export interface DualSessionParty {
  character_id: number
  name: string
  gender?: DualGender | null
}

export interface DualDiceSnapshot {
  roll?: number | null
  lo?: number | null
  hi?: number | null
  effect_tier?: string | null
  yield_mult?: number | null
  duration_sec?: number | null
  label_zh?: string | null
  rerolls_used?: number
  purpose?: string
  max_rerolls?: number
}

export interface DualSession {
  session_id: number
  status: string
  technique_id: string
  technique_label?: string
  mode?: string
  inviter: DualSessionParty
  invitee: DualSessionParty
  invite_expire_at?: string | null
  dice?: DualDiceSnapshot | null
  settle_summary?: Record<string, unknown> | null
}

export interface DualMePayload {
  gender: DualGender | null
  gender_label_zh?: string
  needs_gender: boolean
  session: DualSession | null
  techniques: DualTechnique[]
  config?: {
    invite_expire_sec?: number
    max_rerolls?: number
    spirit_stone_cost?: number
  }
}

export interface DualRankEntry {
  rank: number
  character_id: number
  name: string
  score: number
  gender?: string
}

export interface DualBoardPayload {
  board_key: string
  label_zh: string
  min_score: number
  entries: DualRankEntry[]
  my_rank: number | null
  my_score: number
}

export interface DualRanksPayload {
  boards: Record<string, DualBoardPayload>
  my_gender?: DualGender | null
}
