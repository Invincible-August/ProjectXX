/**
 * M5 世界环境类型：六时 / 天气 / 聚合 env。
 */

/** 六时 ID（服务端权威） */
export type ShichenId =
  | 'dawn'
  | 'noon'
  | 'afternoon'
  | 'dusk'
  | 'night'
  | 'late_night'

/** 天气 ID */
export type WorldWeatherId =
  | 'clear'
  | 'overcast'
  | 'rain'
  | 'hurricane'
  | 'storm'
  | 'thunderstorm'

/** 对当前行为的提示文案 */
export interface WorldEnvHints {
  idle?: string
  breakthrough?: string
  craft?: string
  tribulation?: string
}

/** GET /world/calendar */
export interface WorldCalendarPublic {
  shichen: ShichenId
  shichen_label: string
  next_shichen_at: string
  /** 全日相位可选 */
  phase_index?: number
  calendar_enabled?: boolean
}

/** GET /world/weather */
export interface WorldWeatherPublic {
  weather: WorldWeatherId
  weather_label: string
  region_id?: string
  weather_next_roll_at?: string
}

/** catalog 片段（与 idleEnv.EnvCatalogSnippet 对齐，避免循环依赖用内联） */
export interface WorldEnvCatalogSnippet {
  id?: string
  label?: string
  summary?: string | null
  idle_note?: string | null
  spawn_bias_note?: string | null
  craft_notes?: Record<string, string> | null
  breakthrough_note?: string | null
  tribulation_note?: string | null
}

/** GET /world/env 聚合 */
export interface WorldEnvPublic {
  shichen: ShichenId
  shichen_label: string
  next_shichen_at: string
  weather: WorldWeatherId
  weather_label: string
  weather_next_roll_at?: string
  hints: WorldEnvHints
  calendar_enabled?: boolean
  region_id?: string
  /** 当前时辰/天气玩家可见说明 */
  catalog?: {
    shichen?: WorldEnvCatalogSnippet
    weather?: WorldEnvCatalogSnippet
  }
  /**
   * 世界级挂机预览（无角色灵根/功法标签）。
   * 前端用它实时算「本片预计」，不额外请求。
   */
  idle_preview?: import('./idleEnv').IdleEnvBundle | null
}

/** 嵌入 CharacterPublic 的精简环境摘要 */
export interface WorldEnvSummary {
  shichen: ShichenId
  weather: WorldWeatherId
  next_shichen_at?: string
  shichen_label?: string
  weather_label?: string
}
