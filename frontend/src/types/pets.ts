/**
 * N4/PET-D01 灵宠领域类型。
 */

/** 灵宠战斗面板预览 */
export interface PetStatsPreview {
  atk: number
  hp: number
  speed: number
}

/** 词条实例 */
export interface PetAffixPublic {
  slot_index: number
  affix_type_id: string
  affix_type_name?: string
  kind?: string
  affix_tier: string
  rolled_value: number | string
  locked?: boolean
}

/** 技能摘要 */
export interface PetSkillPublic {
  skill_id: string
  name: string
  power?: number
  accuracy?: number
  category?: string
  priority?: number
  pp?: number
  mutex_tags?: string[]
  missing?: boolean
}

/** 技能栏块 */
export interface PetSkillsBlock {
  equip_slots: number
  skill_pool_id: string
  pool_skill_ids: string[]
  learned: PetSkillPublic[]
  equipped: Array<PetSkillPublic | null>
  learned_ids: string[]
  equipped_ids: Array<string | null>
}

/** PET-D03 被动摘要 */
export interface PetPassivePublic {
  passive_id: string
  name: string
  kind?: string
  effect_domain?: string
  effects?: Record<string, number>
  summary?: string
  missing?: boolean
}

/** 被动块 */
export interface PetPassivesBlock {
  racial_talent: PetPassivePublic | null
  racial_talent_id?: string
  rolled: PetPassivePublic[]
  rolled_ids: string[]
}

/** PET-D04 可喂兽丹 */
export interface PetFeedItemPublic {
  item_id: string
  name: string
  per_item_cap: number
  times_fed: number
  remaining: number | null
  effects: Record<string, number>
  summary?: string
}

/** 喂养块 */
export interface PetFeedBlock {
  total_used: number
  total_cap: number
  items: PetFeedItemPublic[]
  applied_effects?: Record<string, number>
}

/** 数值洗炼费用预览 */
export interface PetValueRerollPreview {
  slot_index: number
  times_already: number
  next_cost_spirit_stones: number
}

/** 灵兽宗改类型费用预览（PET-D06） */
export interface PetTypeRerollPreview {
  slot_index: number
  slot_ordinal?: number
  times_already: number
  next_cost_spirit_stones: number
  eligible: boolean
}

/** GET /pets 单项 */
export interface PetPublic {
  id: number
  species_id: string
  species_name?: string
  race?: string
  race_name?: string
  rarity?: string
  roles?: string[]
  grade?: number
  grade_name?: string
  affix_slot_cap?: number
  type_reroll_slots?: number
  type_reroll_enabled?: boolean
  name?: string
  level: number
  nickname?: string | null
  is_deploy_preferred: boolean
  affixes?: PetAffixPublic[]
  value_reroll_preview?: PetValueRerollPreview[]
  type_reroll_preview?: PetTypeRerollPreview[]
  skills?: PetSkillsBlock
  passives?: PetPassivesBlock
  feed?: PetFeedBlock
  stats?: PetStatsPreview
}

/** 图鉴物种条目 */
export interface PetCatalogSpecies {
  species_id: string
  name: string
  race: string
  race_name: string
  rarity: string
  roles: string[]
  acquire_tags: string[]
  base_atk: number
  base_hp: number
  base_speed: number
  seen: boolean
  caught: boolean
  status: 'unknown' | 'seen' | 'caught' | string
}

/** GET /pets/catalog */
export interface PetCatalogPayload {
  races: Array<{
    race_id: string
    name: string
    racial_talent_id: string
    base_capture_rate: number
  }>
  grades: Array<{
    grade: number
    name: string
    affix_slots: number
    type_reroll_slots: number
    base_mult: number
  }>
  species: PetCatalogSpecies[]
  hold_cap: number
}

/** PET-D05 对战一方 */
export interface PetDuelFighterPublic {
  side: string
  name: string
  hp: number
  max_hp: number
  atk: number
  speed: number
  defending?: boolean
  skills?: PetSkillPublic[]
}

/** PET-D05 对战状态 */
export interface PetDuelState {
  duel_id: string
  seed: number
  round_index: number
  max_rounds: number
  finished: boolean
  winner: string | null
  player: PetDuelFighterPublic
  foe: PetDuelFighterPublic
  events: Array<Record<string, unknown>>
}

/** N5 蛋目录项 */
export interface PetHatchEggPublic {
  egg_item_id: string
  name: string
  species_id: string
  species_name?: string
  hatch_seconds: number
  spirit_stones: number
  owned: number
}

/** N5 孵化会话 */
export interface PetHatchJobPublic {
  job_id: number
  egg_item_id: string
  egg_name?: string
  species_id: string
  species_name?: string
  status: 'hatching' | 'ready' | 'claimed' | string
  started_at?: string
  finish_at?: string
  remaining_seconds?: number
  result_pet_id?: number | null
}

/** GET /pets/hatch */
export interface PetHatchState {
  eggs: PetHatchEggPublic[]
  jobs: PetHatchJobPublic[]
  max_concurrent: number
  hold_cap?: number
  active_count: number
}

/** M4-D04c 遭遇快照 */
export interface PetEncounterPublic {
  encounter_id: string
  region_id: string
  region_label?: string
  shichen: string
  shichen_label?: string
  weather: string
  weather_label?: string
  type: string
  species_id?: string | null
  species_name?: string | null
  grade?: number | null
  special_affix_count?: number
  label?: string
  capturable: boolean
  battle_resolved: boolean
  seed?: number
}

/** 探索预览 */
export interface PetExplorePreview {
  region_id: string
  region_label?: string
  shichen: string
  shichen_label?: string
  weather: string
  weather_label?: string
  skip_battle: boolean
  entries: Array<{
    type?: string
    species_id?: string | null
    species_name?: string | null
    weight: number
    label?: string
    capturable: boolean
  }>
  require_bag: boolean
  bag_ok: boolean
  lure_item_id: string
  lure_count: number
  daily_attempt_cap: number
  auto_capture_enabled: boolean
}

/** 捕获结果（含审计） */
export interface PetCaptureResult {
  success: boolean
  p: number
  factors: Record<string, number>
  roll: number
  seed: number
  encounter?: PetEncounterPublic
  consumed?: Record<string, number>
  acquire_tag?: string
  pet?: PetPublic | null
  id?: number
}
