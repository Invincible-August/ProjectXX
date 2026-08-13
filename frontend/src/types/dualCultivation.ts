/**
 * M7 L7 双修 / 时长榜类型。
 */

export type DualGender = 'male' | 'female'
export type DualBondKind = 'companion' | 'vessel'
export type DualRole = 'number_one' | 'zero'

export interface DualTechnique {
  technique_id: string
  label: string
  mode: 'mutual_gain' | 'transfer' | 'extract'
  mode_label_zh?: string
  require_opposite_gender?: boolean
  base_yield?: number
  [key: string]: unknown
}

export interface DualInviteTarget {
  bond_id: number
  bond_kind: DualBondKind | string
  peer_character_id: number
  peer_name: string
  status: string
  online?: boolean
  peer_major_realm_name?: string | null
  peer_cultivation_points?: number
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
  status_label_zh?: string
  technique_id: string
  technique_label?: string
  mode?: string
  bond_kind?: DualBondKind | string | null
  inviter_role?: DualRole | string
  auto_forced?: boolean
  inviter: DualSessionParty
  invitee: DualSessionParty
  invite_expire_at?: string | null
  undress_expire_at?: string | null
  invitee_undressed?: boolean
  can_undress?: boolean
  can_start?: boolean
  dice?: DualDiceSnapshot | null
  settle_summary?: Record<string, unknown> | null
}

export interface DualMePayload {
  gender: DualGender | null
  gender_label_zh?: string
  needs_gender: boolean
  session: DualSession | null
  techniques: DualTechnique[]
  invite_targets?: {
    companions: DualInviteTarget[]
    vessels: DualInviteTarget[]
    vessel_invite_enabled?: boolean
    hint_zh?: string
  }
  config?: {
    invite_expire_sec?: number
    undress_expire_sec?: number
    max_rerolls?: number
    spirit_stone_cost?: number
    cultivation_gap_scale?: number
  }
}

export interface DualRankEntry {
  rank: number
  character_id: number
  name: string
  score: number
  gender?: string
  score_unit_zh?: string
}

export interface DualBoardPayload {
  board_key: string
  label_zh: string
  min_score: number
  entries: DualRankEntry[]
  my_rank: number | null
  my_score: number
  score_unit_zh?: string
}

export interface DualRanksPayload {
  boards: Record<string, DualBoardPayload>
  my_gender?: DualGender | null
  primary_board?: string
}
