/**
 * 自走棋战报类型（M3；schema_version=1）。
 *
 * 战报零保留：开战响应即完整战报，服务端不落库、无 GET 接口；
 * 前端存 sessionStorage，登出 / 关闭浏览器后销毁。
 */
import type { CharacterPublic } from './character'

/** 棋盘坐标 */
export interface EventCoord {
  x: number
  y: number
}

/** 引擎结构化事件（字段按 type 不同而不同，统一走宽松索引） */
export interface BattleEvent {
  type:
    | 'battle_start'
    | 'battlefield_layer'
    | 'round_start'
    | 'initiative'
    | 'turn_order'
    | 'move'
    | 'hit_check'
    | 'damage'
    | 'obstacle_hit'
    | 'abyss_pass'
    | 'abyss_bounce'
    | 'blocked'
    | 'death'
    | 'battle_end'
    | 'taunt'
    | 'ai_retarget'
    | 'force_shift'
    | string
  seq: number
  [key: string]: unknown
}

/** 战报摘要（simple 档） */
export interface BattleSummary {
  winner: 'attacker' | 'defender' | string
  rounds: number
  survivors: { uid: string; side: number; hp: number }[]
  kills: string[]
}

/** 完整战报包（开战响应内嵌） */
export interface BattleReport {
  schema_version: number
  seed: number
  winner: 'attacker' | 'defender' | string
  rounds: number
  board_text: string
  summary: BattleSummary
  detailed_log: string[]
  events: BattleEvent[]
}

/** 体力读数 */
export interface StaminaState {
  left: number
  cap: number
  next_point_in_seconds: number
  regen_per_minute: number
}

/**
 * 战斗呈现种类（与后端 ``BattleKind`` 对齐）。
 * 播控以后端 ``playback_policy`` 为准，勿按路由猜测。
 */
export type BattleKind =
  | 'exploration'
  | 'dao_contest_live'
  | 'dao_contest_replay'
  | 'duel'
  | 'raid_boss'
  | string

/** 战报播放器播控策略（后端权威） */
export interface PlaybackPolicy {
  allow_simple_mode: boolean
  default_detail: boolean
  allow_play_pause: boolean
  allow_step: boolean
  allow_skip: boolean
  cursor_locked_to_server: boolean
  hold_final_on_reload: boolean
}

/** 旧 sessionStorage / 缺省兜底：日常探索自由回放 */
export const DEFAULT_EXPLORATION_PLAYBACK_POLICY: PlaybackPolicy = {
  allow_simple_mode: true,
  default_detail: false,
  allow_play_pause: true,
  allow_step: true,
  allow_skip: true,
  cursor_locked_to_server: false,
  hold_final_on_reload: false,
}

/** POST /battle/pve 与 /battle/pvp/attack 的响应 */
export interface AutochessBattleResult {
  mode: 'pve' | 'pvp'
  result: 'win' | 'lose'
  seed: number
  monster_id?: string
  monster_name?: string
  target?: {
    character_id: number
    dao_name: string
    realm: { major: string; stage: number; label: string }
  }
  report: BattleReport
  rewards: {
    cultivation_points: number
    spirit_stones: number
  }
  stamina: StaminaState
  character: CharacterPublic
  /** 后端战斗种类（播控矩阵键） */
  battle_kind?: BattleKind
  /** 后端播控策略；缺省按探索自由回放兜底 */
  playback_policy?: PlaybackPolicy
  /** M5：开战锁定的时辰（展示用） */
  locked_shichen?: string
  locked_shichen_label?: string
  /** M5：开战锁定的天气（展示用） */
  locked_weather?: string
  locked_weather_label?: string
}

/** 可挑战怪物（GET /battle/pve/monsters） */
export interface MonsterInfo {
  monster_id: string
  name: string
  stamina_cost: number
  unit_count: number
  rewards_on_win: {
    cultivation_points: number
    spirit_stones: number
  }
  /** M3-D06：编成内嘲讽光环摘要（§0.7 显性；无则空数组） */
  taunt_auras?: Array<{
    aura_id: string
    label_zh: string
    summary: string
  }>
}

/** 可攻打对手（GET /battle/pvp/opponents） */
export interface OpponentInfo {
  character_id: number
  dao_name: string
  major_realm: string
  realm_stage: number
  has_snapshot: boolean
}

/** 本会话战报列表项（前端自生成 key，无服务端 id） */
export interface SessionReportEntry {
  session_key: string
  created_at: string
  mode: 'pve' | 'pvp'
  title: string
  result: 'win' | 'lose'
  payload: AutochessBattleResult
}
