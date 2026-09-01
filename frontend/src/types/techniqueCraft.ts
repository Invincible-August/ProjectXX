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
/** DEV infinite embed cards (admin 角色管理发放). */
export const TECH_CARD_FORMAL_ELEMENT_INF_ID = 'tech_card_formal_element_inf'
export const TECH_CARD_FORMAL_EFFICACY_INF_ID = 'tech_card_formal_efficacy_inf'
/** Printed technique manual catalog id (use from 洞府储物). */
export const TECH_MANUAL_ID = 'tech_manual'

export const TECH_CARD_USEABLE_IDS: ReadonlyArray<string> = [
  TECH_CARD_BLANK_ID,
  TECH_CARD_TYPE_ELEMENT_ID,
  TECH_CARD_TYPE_EFFICACY_ID,
]

export const TECH_CARD_FORMAL_ELEMENT_IDS: ReadonlyArray<string> = [
  TECH_CARD_FORMAL_ELEMENT_ID,
  TECH_CARD_FORMAL_ELEMENT_INF_ID,
]

export const TECH_CARD_FORMAL_EFFICACY_IDS: ReadonlyArray<string> = [
  TECH_CARD_FORMAL_EFFICACY_ID,
  TECH_CARD_FORMAL_EFFICACY_INF_ID,
]

export const TECH_CARD_FORMAL_IDS: ReadonlyArray<string> = [
  ...TECH_CARD_FORMAL_ELEMENT_IDS,
  ...TECH_CARD_FORMAL_EFFICACY_IDS,
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
  jindan: '金丹',
  yuanying: '元婴',
  huashen: '化神',
  true_immortal: '真仙',
}

/** Placeholder affix names from research.yaml technique_craft.affixes. */
const AFFIX_LABELS: Record<string, string> = {
  sa_dust: '余烬',
  sa_edge: '法锋',
  sa_bolt: '法霆',
  sa_pierce: '法破',
  sa_flare: '炎芒',
  sa_void: '虚噬',
  sa_doom: '灭法',
  sb_haze: '薄雾',
  sb_ward: '法盾',
  sb_veil: '法幕',
  sb_bless: '法佑',
  sb_aegis: '灵铠',
  sb_mirror: '玄镜',
  sb_immortal: '不灭障',
  ma_chip: '碎刃',
  ma_edge: '武锋',
  ma_crush: '武摧',
  ma_slash: '武斩',
  ma_break: '破军',
  ma_quake: '震岳',
  ma_kill: '杀劫',
  mb_hide: '皮护',
  mb_ward: '武御',
  mb_guard: '武壁',
  mb_iron: '武罡',
  mb_plate: '玄甲',
  mb_mountain: '镇山',
  mb_diamond: '金刚体',
  is_dust: '散息',
  is_flow: '周天',
  is_tide: '潮汐',
  is_cycle: '归元',
  is_pulse: '脉息',
  is_star: '星河',
  is_dao: '道韵',
  ib_scratch: '皮糙',
  ib_bone: '锻骨',
  ib_marrow: '淬髓',
  ib_tendon: '易筋',
  ib_blood: '换血',
  ib_jade: '玉髓',
  ib_dao: '道体胚',
}

const ATTR_LABELS: Record<string, string> = {
  magic_atk: '法攻',
  magic_def: '法防',
  phys_atk: '物攻',
  phys_def: '物防',
  speed: '速度',
}

const AFFIX_SLOT_STEMS = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']

export const TECHNIQUE_CRAFT_HELP_ZH =
  '于洞府储物开出属性/效能正式卡，点镶嵌格选卡入雏形，确认发动条件与词条后定稿；定稿起于锻体须逐步突破，可废除（须卸装，流通副本保留）。'

export interface TechniqueAffixView {
  id: string
  label_zh: string
  rarity: string
  rarity_label_zh: string
  color: string
  stats: Record<string, number>
  base_stats?: Record<string, number>
}

export interface TechniqueAffixSlot {
  options: string[]
  option_views?: TechniqueAffixView[]
  chosen_id: string | null
  chosen_rarity?: string | null
  chosen_view?: TechniqueAffixView | null
  chosen_level: number
  upgrade_count: number
  reroll_count: number
  next_upgrade_cost?: number | null
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
  /** Present on finalize response only. */
  private?: TechniqueMineFields
}

/** Mine-list extras returned by GET /cave/lab/mine for techniques. */
export interface TechniqueMineFields {
  id: string
  kind?: string
  label_zh: string
  efficacy?: string | null
  cultivable?: boolean
  major_rank?: string | null
  major_rank_label_zh?: string | null
  affix_ids?: string[]
  stats?: Record<string, number>
  upgrade_points?: number
  base?: Record<string, number>
  affixes?: TechniqueAffixSlot[]
  elements?: string[]
  element_limit?: string | null
  weapon_limit?: string | null
  next_rank?: string | null
  next_rank_label_zh?: string | null
  breakthrough_points_required?: number | null
  condition_bonus?: {
    element_limit?: string | null
    weapon_limit?: string | null
    weapon_bonus?: Record<string, number>
    element_bonus?: Record<string, number>
    help_zh?: string
  }
}

export interface TechniqueOriginalView {
  technique_id: string
  label_zh: string
  efficacy: string | null
  major_rank: string
  major_rank_label_zh?: string | null
  upgrade_points: number
  base: Record<string, number>
  affixes: TechniqueAffixSlot[]
  stats: Record<string, number>
  elements?: string[]
  element_limit?: string | null
  weapon_limit?: string | null
  next_rank?: string | null
  next_rank_label_zh?: string | null
  breakthrough_points_required?: number | null
  condition_bonus?: TechniqueMineFields['condition_bonus']
}

export interface TechniqueCultivatePublic {
  technique_id: string
  major_rank: string
  major_rank_label_zh?: string | null
  upgrade_points: number
  base: Record<string, number>
  affixes: TechniqueAffixSlot[]
  stats: Record<string, number>
  next_rank?: string | null
  next_rank_label_zh?: string | null
  breakthrough_points_required?: number | null
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
  return RANK_LABELS[id] || '未知阶'
}

export function affixLabelZh(id: string | null | undefined): string {
  if (!id) return '未选'
  return AFFIX_LABELS[id] || '未知词条'
}

/** Affix column caption: 词条甲 / 词条乙 … (never 「栏1」). */
export function affixSlotLabelZh(index: number): string {
  const stem = AFFIX_SLOT_STEMS[index]
  return stem ? `词条${stem}` : `词条${index + 1}`
}

export function attrLabelZh(id: string): string {
  return ATTR_LABELS[id] || id
}

export function formatAffixStats(stats: Record<string, number> | undefined): string {
  if (!stats || !Object.keys(stats).length) return '无属性'
  return Object.entries(stats)
    .map(([k, v]) => `${attrLabelZh(k)}+${Number(v).toFixed(1).replace(/\.0$/, '')}`)
    .join(' ')
}

export function weaponLabelZh(id: string | null | undefined): string {
  if (!id) return '不选'
  return WEAPON_LIMIT_OPTIONS.find((w) => w.id === id)?.label_zh || id
}

export function emptyAffixSlot(): TechniqueAffixSlot {
  return {
    options: [],
    option_views: [],
    chosen_id: null,
    chosen_rarity: null,
    chosen_view: null,
    chosen_level: 0,
    upgrade_count: 0,
    reroll_count: 0,
    next_upgrade_cost: null,
  }
}

function asAffixView(raw: unknown): TechniqueAffixView | null {
  if (!raw || typeof raw !== 'object') return null
  const row = raw as Record<string, unknown>
  const id = String(row.id || '')
  if (!id) return null
  const statsRaw = row.stats && typeof row.stats === 'object' ? (row.stats as Record<string, unknown>) : {}
  const stats: Record<string, number> = {}
  for (const [k, v] of Object.entries(statsRaw)) {
    stats[k] = Number(v || 0)
  }
  return {
    id,
    label_zh: String(row.label_zh || AFFIX_LABELS[id] || '未知词条'),
    rarity: String(row.rarity || 'white'),
    rarity_label_zh: String(row.rarity_label_zh || row.rarity || '白'),
    color: String(row.color || '#eceff1'),
    stats,
  }
}

export function asAffixSlots(raw: unknown): TechniqueAffixSlot[] {
  if (!Array.isArray(raw) || raw.length === 0) {
    return [emptyAffixSlot()]
  }
  return raw.map((cell) => {
    const row = cell && typeof cell === 'object' ? (cell as Record<string, unknown>) : {}
    const options = Array.isArray(row.options) ? row.options.map((x) => String(x)) : []
    const optionViews = Array.isArray(row.option_views)
      ? (row.option_views.map(asAffixView).filter(Boolean) as TechniqueAffixView[])
      : []
    return {
      options,
      option_views: optionViews,
      chosen_id: row.chosen_id == null || row.chosen_id === '' ? null : String(row.chosen_id),
      chosen_rarity:
        row.chosen_rarity == null || row.chosen_rarity === ''
          ? null
          : String(row.chosen_rarity),
      chosen_view: asAffixView(row.chosen_view),
      chosen_level: Number(row.chosen_level || 0),
      upgrade_count: Number(row.upgrade_count || 0),
      reroll_count: Number(row.reroll_count || 0),
      next_upgrade_cost:
        row.next_upgrade_cost == null ? null : Number(row.next_upgrade_cost),
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
