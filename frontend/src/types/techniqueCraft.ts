/**
 * Technique self-research (P1 card craft) DTOs.
 * Align with backend app.constants.technique_craft / TechniqueDraftPublic.
 */

/** Blank / type / formal catalog ids. */
export const TECH_CARD_BLANK_ID = 'tech_card_blank'
export const TECH_CARD_TYPE_ELEMENT_ID = 'tech_card_type_element'
export const TECH_CARD_TYPE_EFFICACY_ID = 'tech_card_type_efficacy'
export const TECH_CARD_FORMAL_ELEMENT_ID = 'tech_card_formal_element'
export const TECH_CARD_FORMAL_EFFICACY_ID = 'tech_card_formal_efficacy'
/** Printed technique manual catalog id (use from lab bag list). */
export const TECH_MANUAL_ID = 'tech_manual'

export const TECH_CARD_USEABLE_IDS: ReadonlyArray<string> = [
  TECH_CARD_BLANK_ID,
  TECH_CARD_TYPE_ELEMENT_ID,
  TECH_CARD_TYPE_EFFICACY_ID,
]

export const TECH_CARD_FORMAL_IDS: ReadonlyArray<string> = [
  TECH_CARD_FORMAL_ELEMENT_ID,
  TECH_CARD_FORMAL_EFFICACY_ID,
]

export const TECH_CARD_ALL_IDS: ReadonlyArray<string> = [
  ...TECH_CARD_USEABLE_IDS,
  ...TECH_CARD_FORMAL_IDS,
]

export const ATTACK_EFFICACIES: ReadonlySet<string> = new Set([
  'spell_attack',
  'martial_attack',
])

/** Only idle efficacies can occupy the main-technique slot. */
export const IDLE_EFFICACIES: ReadonlySet<string> = new Set([
  'idle_spirit',
  'idle_body',
])

export const WEAPON_LIMIT_OPTIONS: ReadonlyArray<{ id: string; label_zh: string }> = [
  { id: 'sword', label_zh: '剑' },
  { id: 'saber', label_zh: '刀' },
  { id: 'spear', label_zh: '枪' },
  { id: 'gauntlet', label_zh: '拳套' },
  { id: 'bow', label_zh: '弓' },
  { id: 'puppet', label_zh: '傀儡' },
  { id: 'avatar', label_zh: '化身' },
]

const ELEMENT_LABELS: Record<string, string> = {
  metal: '金',
  wood: '木',
  water: '水',
  fire: '火',
  earth: '土',
  wind: '风',
  thunder: '雷',
}

const EFFICACY_LABELS: Record<string, string> = {
  spell_attack: '攻击法术',
  spell_buff: '增益法术',
  martial_attack: '攻击武技',
  martial_buff: '增益武技',
  idle_spirit: '修为修炼',
  idle_body: '炼体修炼',
}

const RANK_LABELS: Record<string, string> = {
  body_tempering: '锻体',
  qi_refining: '炼气',
  foundation: '筑基',
}

/** Placeholder affix names from research.yaml technique_craft.affixes. */
const AFFIX_LABELS: Record<string, string> = {
  sa_edge: '法锋',
  sb_ward: '法盾',
  ma_edge: '武锋',
  mb_ward: '武御',
  is_flow: '周天',
  ib_bone: '锻骨',
}

export const TECHNIQUE_CRAFT_HELP_ZH =
  '用空白卡生成属性/效能正式卡，镶入草稿后选发动条件与词条，定稿后可培养。'

export interface TechniqueAffixSlot {
  options: string[]
  chosen_id: string | null
  chosen_level: number
  upgrade_count: number
  reroll_count: number
}

export interface TechniqueDraftPublic {
  id: number
  phase: string
  elements: string[]
  efficacy: string | null
  can_finalize: boolean
  label_zh: string
  major_rank: string
  element_limit: string | null
  weapon_limit: string | null
  upgrade_points: number
  base: Record<string, number>
  affixes: TechniqueAffixSlot[]
  technique_id?: string
}

export interface TechniqueCultivatePublic {
  technique_id: string
  major_rank: string
  upgrade_points: number
  base: Record<string, number>
  affixes: TechniqueAffixSlot[]
  stats: Record<string, number>
}

/** Mine-list extras returned by GET /cave/lab/mine for techniques. */
export interface TechniqueMineFields {
  id: string
  kind?: string
  label_zh: string
  efficacy?: string | null
  cultivable?: boolean
  major_rank?: string | null
  affix_ids?: string[]
  stats?: Record<string, number>
}

export interface TechniqueOriginalView {
  technique_id: string
  label_zh: string
  efficacy: string | null
  major_rank: string
  upgrade_points: number
  base: Record<string, number>
  affixes: TechniqueAffixSlot[]
  stats: Record<string, number>
}

export function elementLabelZh(id: string): string {
  return ELEMENT_LABELS[id] || id
}

export function efficacyLabelZh(id: string | null | undefined): string {
  if (!id) return '未镶嵌'
  return EFFICACY_LABELS[id] || id
}

export function rankLabelZh(id: string | null | undefined): string {
  if (!id) return '—'
  return RANK_LABELS[id] || id
}

export function affixLabelZh(id: string | null | undefined): string {
  if (!id) return '未选'
  return AFFIX_LABELS[id] || id
}

export function weaponLabelZh(id: string | null | undefined): string {
  if (!id) return '不选'
  return WEAPON_LIMIT_OPTIONS.find((w) => w.id === id)?.label_zh || id
}

export function emptyAffixSlot(): TechniqueAffixSlot {
  return {
    options: [],
    chosen_id: null,
    chosen_level: 0,
    upgrade_count: 0,
    reroll_count: 0,
  }
}

export function asAffixSlots(raw: unknown): TechniqueAffixSlot[] {
  if (!Array.isArray(raw) || raw.length === 0) {
    return [emptyAffixSlot()]
  }
  return raw.map((cell) => {
    const row = cell && typeof cell === 'object' ? (cell as Record<string, unknown>) : {}
    const options = Array.isArray(row.options) ? row.options.map((x) => String(x)) : []
    return {
      options,
      chosen_id: row.chosen_id == null || row.chosen_id === '' ? null : String(row.chosen_id),
      chosen_level: Number(row.chosen_level || 0),
      upgrade_count: Number(row.upgrade_count || 0),
      reroll_count: Number(row.reroll_count || 0),
    }
  })
}

/**
 * Map mine-list `affix_ids` into cultivate slots so upgrade stays clickable
 * before a cultivate POST hydrates levels.
 */
export function affixSlotsFromIds(ids: unknown): TechniqueAffixSlot[] {
  if (!Array.isArray(ids) || ids.length === 0) {
    return asAffixSlots([])
  }
  const chosen = ids.map((id) => String(id || '').trim()).filter((id) => id.length > 0)
  if (!chosen.length) {
    return asAffixSlots([])
  }
  return chosen.map((id) => ({
    options: [id],
    chosen_id: id,
    chosen_level: 0,
    upgrade_count: 0,
    reroll_count: 0,
  }))
}
