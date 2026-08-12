/**
 * M4 工坊领域类型（配方 / 队列 / 执行者）。
 */

/** 工坊五分支 */
export type CraftBranch = 'alchemy' | 'smithing' | 'talisman' | 'array' | 'puppet'

/** 队列执行者：本体或化身 */
export type CraftActor = 'main' | 'avatar'

/** 配方材料项 */
export interface CraftMaterial {
  item_id: string
  quantity: number
}

/** GET /craft/recipes 单项 */
export interface CraftRecipe {
  recipe_id: string
  branch: CraftBranch | string
  name: string
  duration_seconds: number
  fail_chance: number
  spirit_stone_cost: number
  stamina_cost: number
  materials: CraftMaterial[]
  locked: boolean
  lock_reason?: string | null
  /** 本体制造业挂机效率加成（来自 craft_recipes.yaml） */
  main_crafting_bonus?: number
}

/** 工坊任务状态 */
export type CraftJobStatus = 'running' | 'ready' | 'claimed' | 'failed' | string

/** GET /craft/jobs 单项 */
export interface CraftJob {
  id: number
  actor: CraftActor | string
  recipe_id: string
  status: CraftJobStatus
  started_at: string
  finish_at: string
  result?: Record<string, unknown> | null
  /** M5：开工时锁定的天气 */
  locked_weather?: string
  locked_weather_label?: string
  locked_shichen?: string
  locked_shichen_label?: string
}

/** 工坊队列摘要（character.craft_jobs_summary） */
export interface CraftJobsSummary {
  running: number
  ready: number
}

/** POST /craft/claim 响应 */
export interface CraftClaimResult {
  job_id: number
  failed: boolean
  outputs?: Array<Record<string, unknown>>
}
