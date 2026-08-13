/**
 * 角色领域类型（对齐 M0～M5 CharacterPublic）。
 */

import type {
  AvatarSummary,
  DivineSenseSummary,
  DualIdlePreview,
} from './avatar'
import type { CraftJobsSummary } from './craft'
import type { DaoPublic } from './dao'
import type { DaoLordSummary } from './daoLord'
import type { SectSummary } from './sect'
import type { FerryPublic } from './ferry'
import type { StoryFlagsPublic } from './reincarnation'
import type { TribulationSummary } from './tribulation'
import type { WorldEnvSummary } from './world'
import type { IdleEnvBundle } from './idleEnv'
import type { ActivitySnapshot } from './activity'

/** M5 角色状态机 */
export type CharacterStatus =
  | 'normal'
  | 'breaking_through'
  | 'tribulation'
  | 'awaiting_ferry'
  | 'reincarnating'
  | string

/** 离线待领取明细（与后端 pending_offline_json 对齐） */
export interface OfflinePending {
  /** 离线区间起点 UTC ISO */
  from?: string
  /** 实际结算终点（可能被离线帽截断） */
  to_effective?: string
  /** 适用离线帽小时数 */
  cap_hours: number
  /** 是否因离线帽截断 */
  capped: boolean
  /** 墙钟流逝秒数 */
  wall_elapsed_seconds: number
  /** 已结算 tick 数 */
  settled_ticks: number
  /** 离线时挂机方向 */
  direction: string
  /** 待领修灵池增量 */
  gained_cultivation: number
  /** 待领炼体池增量 */
  gained_body: number
  /** 待领制造业经验 */
  gained_crafting: number
  /** 已扣灵石 */
  spent_spirit_stones: number
  /** 是否因灵石不足停滞 */
  is_stalled: boolean
}

/** 功法摘要 */
export interface TechniqueSummaryItem {
  id: string
  name: string
  level: number
  max_level: number
  track?: string
}

/** 体质镶嵌摘要 */
export interface ConstitutionSummary {
  equipped: Array<{
    slot_type: string
    slot_index: number
    name?: string
    def_id?: string
  }>
}

/** ATTR 战斗属性块（服务端权威） */
export interface CombatAttrBlock {
  schema_version?: number
  entity_kind?: string
  final: Record<string, number>
  primary?: Record<string, number>
  labels?: Record<string, string>
  breakdown?: Array<Record<string, unknown>>
  growth?: Record<string, number | string>
}

/** ATTR 生活属性块 */
export interface LifeAttrBlock {
  schema_version?: number
  final: Record<string, number>
  labels?: Record<string, string>
  breakdown?: Array<Record<string, unknown>>
}

/** M4 类型再导出（单源在 avatar.ts / craft.ts） */
export type {
  AvatarSummary,
  DivineSenseSummary,
  DualIdlePreview,
} from './avatar'
export type { CraftJobsSummary } from './craft'

/** 对外角色结构 CharacterPublic */
export interface CharacterPublic {
  /** 角色主键 */
  id: number
  /** 道号（全服唯一） */
  name: string
  /** 大境界键，如 body_tempering */
  major_realm: string
  /** 大境界中文名 */
  major_realm_name: string
  /** 境界层/期序号 */
  realm_stage: number
  /** 层/期标签键，如 layer_1 / early */
  realm_stage_label: string
  /** 境界展示文案 */
  realm_display: string
  /** 修灵池（未投入境界进度的修为点数） */
  cultivation_points: number
  /** 炼体池 */
  body_tempering_points: number
  /** 炼体大境 id（炼皮→道体） */
  body_temper_stage?: string
  /** 炼体大境中文名 */
  body_temper_stage_name?: string
  /** 炼体层/期序号 */
  body_temper_layer?: number
  /** 炼体层/期标签 */
  body_temper_layer_label?: string
  /** 当前档淬体进度 */
  body_temper_progress?: number
  /** 距本档圆满尚需；可淬体时为 0 */
  body_temper_to_next?: number | null
  /** 淬体进度比例 0～1 */
  body_temper_progress_ratio?: number
  /** 炼体程度展示文案 */
  body_temper_display?: string
  /** 进度已满但主修未达对照境 */
  body_temper_capped?: boolean
  /** 可发起淬体 */
  body_temper_ready_to_quench?: boolean
  /** 淬体目标展示名 */
  body_temper_next_stage_name?: string | null
  /** 制造业经验池 */
  crafting_exp: number
  /** 灵石 */
  spirit_stones: number
  /** 本体挂机方向：none/spirit/body/crafting/sect_mining */
  idle_direction: string
  idle_direction_name: string
  /** 状态机：normal / tribulation / awaiting_ferry 等 */
  status: CharacterStatus
  status_name: string
  /** 上次挂机 settle 锚点 UTC ISO */
  last_settled_at: string
  created_at: string
  updated_at: string
  /** 距下一档突破尚需投入的进度提示 */
  cultivation_to_next: number | null
  /** 境界进度比例（基于 realm_progress） */
  cultivation_progress_ratio: number
  /** 灵石不足导致挂机停滞 */
  is_stalled: boolean
  idle_cultivation_per_tick: number
  idle_body_per_tick?: number
  idle_crafting_per_tick?: number
  idle_stones_per_tick: number
  idle_tick_seconds: number
  /** 衍生基础攻击（= combat.final.phys_atk 别名） */
  base_atk: number
  /** 衍生基础生命（= combat.final.hp 别名） */
  base_hp: number
  /** ATTR 战斗属性块 */
  combat?: CombatAttrBlock | null
  /** ATTR 生活属性块 */
  life?: LifeAttrBlock | null
  /** 战斗体力（惰性恢复后）：left/cap/regen_per_minute/next_point_in_seconds */
  battle_stamina?: {
    left: number
    cap: number
    next_point_in_seconds?: number
    regen_per_minute?: number
  } | null
  /** M2：已投入当前档的境界进度（突破门槛） */
  realm_progress: number
  /** 最近跨境品阶键；无跨境为 none */
  breakthrough_grade: string
  breakthrough_grade_name: string
  /** 由品阶推导的神通槽位数 */
  divine_ability_slots: number
  /** 会员档：free/tier1/tier2 */
  membership_tier: string
  /** 付费会员过期 UTC ISO；free 为 null */
  membership_expires_at?: string | null
  /** 离线收益上限小时数 */
  offline_cap_hours: number
  /** 天道点（不可玩家直转） */
  tiandao_points?: number
  /** 会员摘要 */
  membership?: {
    tier?: string
    label_zh?: string
    expires_at?: string | null
    idle_cap_hours?: number
  } | null
  offline_pending: OfflinePending | null
  /** 待领取事件日志（师傅传授等）；有离线收益时随领取带回，否则前端 ack 清空 */
  pending_event_logs?: Array<{
    message: string
    level?: string
    source?: string
    at?: string
  }>
  technique_summary?: TechniqueSummaryItem[]
  constitution_summary?: ConstitutionSummary
  // --- M4 双线程成长 ---
  /** 是否已凝练化身 */
  has_avatar?: boolean
  avatar_summary?: AvatarSummary | null
  /** 神识容量与占用 */
  divine_sense?: DivineSenseSummary | null
  /** 阵法制造等级 */
  array_craft_level?: number
  craft_jobs_summary?: CraftJobsSummary
  inventory_count?: number
  pets_count?: number
  dual_idle_preview?: DualIdlePreview | null
  // --- M5 环境与轮回 ---
  /** 待引渡摘要；非待引渡时为 null */
  ferry?: FerryPublic | null
  /** 轮回点（跨世货币） */
  reincarnation_points?: number
  /** 已完成轮回次数 */
  reincarnation_count?: number
  /** 历史最高大境界 */
  peak_major_realm?: string
  /** 轮回成长属性占位 */
  growth_attrs?: Record<string, number | string> | null
  /** 跨世永久加成（独立表） */
  permanent_bonus?: {
    initial_attr_bonus?: number
    minor_growth_bonus?: number
    major_growth_bonus?: number
    break_rate_bonus?: number
    lifetime_applied_growth?: number
    constitution_slots_bought?: number
    spirit_root_slots_bought?: number
  } | null
  /** 剧情已历节点等 flag */
  story_flags?: StoryFlagsPublic | null
  /** 进行中渡劫会话摘要 */
  tribulation?: TribulationSummary | null
  /** 嵌入的世界环境摘要 */
  world_env?: WorldEnvSummary | null
  /** 气运（渡劫轴 A：高则降威力） */
  fate_luck?: number
  /** 魔性（渡劫轴 A：高则抬威力） */
  demonic_nature?: number
  /** 挂机环境有效速率 + catalog 说明（时辰×天气×灵根/功法标签） */
  idle_env?: IdleEnvBundle | null
  /** 灵根环境标签（参与 tag_modifiers） */
  spirit_root_tags?: string[]
  /** 活动互斥快照（修炼/工坊/渡劫等） */
  activity?: ActivitySnapshot | null
  // --- M6 大道与道主 ---
  /** 本命道 / 道值 / 等级摘要；未开道亦可有 can_open */
  dao?: DaoPublic | null
  /** 自己是某道道主时的印记；否则 null */
  dao_lord?: DaoLordSummary | null
  // --- M7 宗门 ---
  /** 宗门摘要（散修亦有 in_sect=false 占位）；系统关闭时可为 null */
  sect?: SectSummary | null
  // --- M7 L7 性别 ---
  /** male | female；未补选为 null */
  gender?: 'male' | 'female' | null
  gender_label_zh?: string | null
  // --- M7 L2 社交 ---
  /** 活跃道友数 */
  friend_count?: number
  /** 社交角标：mail_unread / chat_unread / dual_invite 等 */
  social_badges?: {
    mail_unread?: number
    chat_unread?: number
    dual_invite?: number
    [key: string]: number | undefined
  } | null
}

/** POST /characters 请求体 */
export interface CreateCharacterPayload {
  /** 角色名：2～16，中文/字母/数字 */
  name: string
  /** 道途阴阳：创角必选 */
  gender: 'male' | 'female'
}
