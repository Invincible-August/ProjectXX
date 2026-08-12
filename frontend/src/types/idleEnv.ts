/**
 * M5 挂机环境预览类型（CharacterPublic.idle_env / /world/env.idle_preview）。
 */

/** 乘区拆解一行 */
export interface EnvMultBreakdownItem {
  source:
    | 'realm_base'
    | 'shichen'
    | 'weather'
    | 'tag_shichen'
    | 'tag_weather'
    | 'constitution'
    | 'equipment'
    | 'buff_pill'
    | 'buff_talisman'
    | 'spirit_eye'
    | 'cave'
    | string
  id: string
  label: string
  mult: number
}

/** 时辰/天气 catalog 片段（玩家可见说明） */
export interface EnvCatalogSnippet {
  id: string
  label: string
  summary?: string | null
  idle_note?: string | null
  spawn_bias_note?: string | null
  /** 炼丹/炼器等分支说明 */
  craft_notes?: Record<string, string> | null
  breakthrough_note?: string | null
  tribulation_note?: string | null
}

/** 单一修炼方向的有效速率预览 */
export interface IdleDirectionEnvPreview {
  base_per_tick: number
  effective_per_tick: number
  total_mult: number
  breakdown: EnvMultBreakdownItem[]
  shichen: EnvCatalogSnippet
  weather: EnvCatalogSnippet
}

/** 角色挂机环境包（按方向） */
export interface IdleEnvBundle {
  spirit: IdleDirectionEnvPreview
  body: IdleDirectionEnvPreview
  crafting: IdleDirectionEnvPreview
  /** 采矿个人灵石/周天（可选；旧包无此键） */
  sect_mining?: IdleDirectionEnvPreview
  tags_applied: string[]
}
