/**
 * M4 工坊领域类型（配方 / 队列 / 执行者）。
 */

/** 工坊制造业分支（阵法不进工坊） */
export type CraftBranch = 'alchemy' | 'smithing' | 'talisman' | 'puppet' | 'array'

/** 工坊页外层分支钮（与后端 workshop branch 协议对齐） */
export const CRAFT_BRANCH_TABS: ReadonlyArray<{ key: CraftBranch; label: string }> = [
  { key: 'alchemy', label: '炼丹' },
  { key: 'smithing', label: '炼器' },
  { key: 'talisman', label: '符箓' },
  { key: 'puppet', label: '傀儡' },
]

/** 队列执行者：本体或化身 */
export type CraftActor = 'main' | 'avatar'

/** 配方材料项 */
export interface CraftMaterial {
  item_id: string
  quantity: number
  /** 玩家可见中文名 */
  label_zh?: string
}

/** GET /craft/talisman/preload 单格 */
export interface TalismanPreloadSlot {
  inventory_item_id: number
  item_id: string
  quantity: number
  label_zh: string
  effect_id?: string | null
}

/** GET /craft/talisman/preload */
export interface TalismanPreloadPayload {
  slots: TalismanPreloadSlot[]
  max_slots: number
}

/** GET /craft/recipes 成品悬停 */
export interface CraftRecipeInspectElement {
  id: string
  label_zh: string
  border?: string
}

export interface CraftRecipeInspectTag {
  id: string
  label_zh: string
}

/** 成品悬停：单一属性 + 功效 + 境界门槛 */
export interface CraftRecipeInspect {
  craft_level_label_zh: string
  required_craft_level: number
  realm_req_zh: string
  help_zh: string
  effects: CraftRecipeInspectTag[]
  element?: CraftRecipeInspectElement | null
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
  required_craft_level?: number
  recipe_tier?: number
  craft_level?: number
  /** 成品基础效果（服务端中文） */
  effect_zh?: string
  /** 成品悬停条件栏 */
  inspect?: CraftRecipeInspect
  materials: CraftMaterial[]
  locked: boolean
  lock_reason?: string | null
  /** 本体制造业挂机效率加成（来自 craft_recipes.yaml） */
  main_crafting_bonus?: number
  /** 炼器部位组（武器/头部/护手…）；矿板等为空 */
  equip_slot_group?: string | null
  equip_slot_group_zh?: string | null
  /** 符箓功能：buff / offensive / curse */
  talisman_kind?: string | null
  talisman_kind_zh?: string | null
}

/** 成品属性 id；无属性为空串 */
export function recipeElementId(recipe: CraftRecipe): string {
  return recipe.inspect?.element?.id || ''
}

/** 制作等级门槛 */
export function recipeRequiredLevel(recipe: CraftRecipe): number {
  return recipe.inspect?.required_craft_level ?? recipe.required_craft_level ?? 0
}

/** 炼器部位组；非装备产出为空串 */
export function recipeEquipSlotGroup(recipe: CraftRecipe): string {
  return recipe.equip_slot_group || ''
}

/** 符箓功能 kind；无挂载为空串 */
export function recipeTalismanKind(recipe: CraftRecipe): string {
  return recipe.talisman_kind || ''
}

/** 工坊任务状态 */
export type CraftJobStatus = 'running' | 'ready' | 'claimed' | 'failed' | string

/** GET /craft/jobs 单项 */
export interface CraftJob {
  id: number
  actor: CraftActor | string
  recipe_id: string
  /** 一次制造件数 */
  quantity?: number
  status: CraftJobStatus
  started_at: string
  finish_at: string
  total_finish_at?: string
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
