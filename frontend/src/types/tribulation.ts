/**
 * M5 渡劫会话类型（双维雷劫 + 准备格）。
 */
import type { CharacterPublic } from './character'
import type { ShichenId, WorldWeatherId } from './world'

/** 威力档：怜悯 / 普通 / 天妒 / 灭世（遮天） */
export type TribulationPowerTier = 'mercy' | 'normal' | 'jealousy' | 'apocalypse'

/** 次数档：九 / 八十一（前端 hundred） / 千 / 万 */
export type TribulationCountTier = 'nine' | 'hundred' | 'thousand' | 'myriad'

/** 会话阶段：准备 → 确认 → 进行 → 胜/败/陨落 */
export type TribulationPhase =
  | 'preparing'
  | 'committed'
  | 'running'
  | 'won'
  | 'failed'
  | 'fallen'

/** 准备格单项（护劫道具；轴 B 承伤） */
export interface TribulationPrepSlot {
  /** 格子序号 */
  slot: number
  item_uid?: string
  item_name?: string
  /** 普通法宝等低效抵劫标记 */
  inefficient?: boolean
}

/** 表现天气：劫云或世界天气 */
export type TribulationDisplayWeather = 'tribulation_cloud' | WorldWeatherId

/** GET /tribulation/me 会话体 */
export interface TribulationSessionPublic {
  id: number
  phase: TribulationPhase
  /** 阶段中文（§0.0.2） */
  phase_label_zh?: string
  /** 目标境界展示文案 */
  target_label: string
  /** 预估突破品阶（映射雷劫双维） */
  projected_grade?: string
  /** 预估品阶中文名 */
  projected_grade_name?: string
  /** 威力品阶键 */
  power_tier: TribulationPowerTier
  power_label: string
  /** 次数档键 */
  count_tier: TribulationCountTier
  count_label: string
  /** 总雷击数 */
  strike_total: number
  /** 已结算雷击数 */
  strike_done: number
  /** 开渡锁定时辰 */
  locked_shichen: ShichenId
  locked_shichen_label?: string
  /** 开渡锁定天气（伤害用锁前天气） */
  locked_weather: WorldWeatherId
  locked_weather_label?: string
  /** 展示天气（开渡后可为劫云） */
  display_weather: TribulationDisplayWeather
  display_weather_label?: string
  /** 在既有劫云内开渡 → 基础伤害翻倍 */
  in_cloud_double: boolean
  /** 劫云半径 */
  cloud_radius: number
  hp_current: number
  hp_max: number
  prep_slots: TribulationPrepSlot[]
  /** 可选阵法 id（轴 A） */
  formation_id?: string | null
  /** 是否选用遮天 */
  veil_selected?: boolean
  veil_result?: 'success' | 'fail' | null
  /** 灵宝护主是否已触发 */
  guardian_used: boolean
  /** 轴 A 威力 / 轴 B 承伤提示文案 */
  axis_hints?: { power?: string; mitigation?: string }
  /** 批次摘要日志 */
  batch_log?: string[]
  /** 气运占位 */
  fate_luck?: number
  /** 魔性占位 */
  demonic_nature?: number
}

/** 角色面板上的渡劫摘要 */
export interface TribulationSummary {
  id?: number
  phase?: TribulationPhase
  power_label?: string
  count_label?: string
  strike_done?: number
  strike_total?: number
  target_label?: string
}

/** PUT /tribulation/prep 请求体 */
export interface TribulationPrepPayload {
  slots: Array<{ slot: number; item_uid?: string | null }>
  formation_id?: string | null
  veil_selected?: boolean
}

/** 批次结算事件摘要 */
export interface TribulationBatchEvent {
  type: string
  text: string
  damage?: number
  [key: string]: unknown
}

/** resolve-batch / auto-resolve / begin 等突变响应 */
export interface TribulationMutationResult {
  session: TribulationSessionPublic
  character?: CharacterPublic
  events?: TribulationBatchEvent[]
  message?: string
  finished?: boolean
}

/** 遮天失败副作用（服务端加权表抽出，只展示） */
export interface TribulationVeilFailEffect {
  id: string
  label: string
  raise_power_tier: boolean
  force_cloud_double: boolean
  hp_damage_ratio: number
}

/** 遮天检定结果 */
export interface TribulationVeilResult {
  session: TribulationSessionPublic
  /** 服务端权威：success | fail */
  veil_outcome: 'success' | 'fail' | string
  veil_fail_effect?: TribulationVeilFailEffect | null
  /** 兼容旧字段 */
  success?: boolean
  message?: string
  character?: CharacterPublic
}
