/**
 * Format item/equipment attributes into the shared hover card model.
 */
import type { ConstitutionBag } from '../types/constitution'
import type { CraftRecipe } from '../types/craft'
import type { DivineAbilityItem, DivineAbilitySlotView } from '../types/divineAbilities'
import type { EquipmentSlotPublic, EquipmentStatPreview } from '../types/equipment'
import type { ItemHoverModel, ItemHoverStat } from '../types/itemHover'
import type { TechniqueItem, TechniqueSlotView } from '../types/techniques'

const GRADE_ZH: Record<string, string> = {
  inferior: '劣质',
  mortal: '凡品',
  good: '良品',
  superior: '上品',
  peerless: '极品',
  immortal: '仙品',
  heavenly: '天道',
}

const CONSTITUTION_EFFECT_ZH: Record<string, string> = {
  hp_bonus: '生命',
  atk_bonus: '攻击',
  idle_mult: '挂机',
  vitality: '气血',
  defense: '防御',
}

export function shortItemName(name: string, max = 4): string {
  const parts = name.split(/[·・]/)
  const tail = (parts[parts.length - 1] || name).trim()
  return tail.slice(0, max)
}

export function gradeLabelZh(raw: string | undefined): string {
  const key = String(raw || '').trim()
  if (!key) return ''
  return GRADE_ZH[key] || key
}

function signedNumber(key: string, raw: number): string {
  if (key.endsWith('_mult')) return `×${raw}`
  if (raw > 0) return `+${raw}`
  return String(raw)
}

export function statsFromPreview(
  preview: Record<string, EquipmentStatPreview> | undefined,
): ItemHoverStat[] {
  return Object.values(preview ?? {}).map((row) => ({
    label_zh: row.label_zh,
    value: signedNumber('flat', Number(row.value)),
  }))
}

export function statsFromEffectMap(
  effects: Record<string, number> | undefined,
  prefixZh?: string,
): ItemHoverStat[] {
  const rows: ItemHoverStat[] = []
  for (const [key, raw] of Object.entries(effects ?? {})) {
    const label = CONSTITUTION_EFFECT_ZH[key] || key
    const value = Number(raw)
    if (Number.isNaN(value)) continue
    rows.push({
      label_zh: prefixZh ? `${prefixZh} ${label}` : label,
      value: signedNumber(key, value),
    })
  }
  return rows
}

export function hoverFromEquipment(args: {
  name: string
  slotLabelZh?: string
  stats?: Record<string, EquipmentStatPreview>
  empty?: boolean
}): ItemHoverModel {
  if (args.empty) {
    return { name: args.slotLabelZh || '空', helpZh: '此部位尚未穿戴' }
  }
  return {
    name: args.name,
    cornerZh: args.slotLabelZh,
    stats: statsFromPreview(args.stats),
  }
}

export function hoverFromSlotPublic(cell: EquipmentSlotPublic | undefined): ItemHoverModel {
  if (!cell) return { name: '空' }
  if (!cell.item_uid) {
    return hoverFromEquipment({ name: '', slotLabelZh: cell.slot_label_zh, empty: true })
  }
  return hoverFromEquipment({
    name: cell.item_label_zh || '装备',
    slotLabelZh: cell.slot_label_zh,
    stats: cell.stats_preview,
  })
}

export function hoverFromTechnique(item: {
  name: string
  source_label_zh?: string
  level?: number
  max_level?: number
  elements?: TechniqueItem['elements']
  help_zh?: string
}): ItemHoverModel {
  const level = item.level
  const maxLevel = item.max_level
  return {
    name: item.name,
    cornerZh: item.source_label_zh,
    subtitle:
      level != null && maxLevel != null ? `lv.${level}/lv.${maxLevel}` : undefined,
    elements: item.elements,
    helpZh: item.help_zh,
  }
}

export function hoverFromTechniqueSlot(slot: TechniqueSlotView): ItemHoverModel | null {
  if (!slot.technique_id || !slot.name) return null
  return hoverFromTechnique({
    name: slot.name,
    source_label_zh: slot.source_label_zh,
    level: slot.level,
    max_level: slot.max_level,
    elements: slot.elements,
    help_zh: slot.help_zh,
  })
}

export function hoverFromDivine(
  item: Pick<
    DivineAbilityItem,
    'name' | 'source_label_zh' | 'elements' | 'help_zh' | 'effect_zh'
  >,
): ItemHoverModel {
  return {
    name: item.name,
    cornerZh: item.source_label_zh,
    elements: item.elements,
    helpZh: item.effect_zh || item.help_zh,
  }
}

export function hoverFromDivineSlot(slot: DivineAbilitySlotView): ItemHoverModel | null {
  if (!slot.ability_id || !slot.name) return null
  return hoverFromDivine({
    name: slot.name,
    source_label_zh: slot.source_label_zh,
    elements: slot.elements,
    help_zh: slot.help_zh,
    effect_zh: slot.effect_zh,
  })
}

export function hoverFromConstitution(item: ConstitutionBag): ItemHoverModel {
  const corner = gradeLabelZh(item.grade || item.quality)
  return {
    name: item.name,
    cornerZh: corner || undefined,
    stats: [
      ...statsFromEffectMap(item.main_effects, '本源'),
      ...statsFromEffectMap(item.sub_effects, '旁支'),
    ],
  }
}

export function hoverFromRecipe(recipe: CraftRecipe): ItemHoverModel {
  const inspect = recipe.inspect
  const levelLabel = inspect?.craft_level_label_zh || '制作等级'
  const required = inspect?.required_craft_level ?? recipe.required_craft_level ?? 0
  const el = inspect?.element
  return {
    name: recipe.name,
    cornerZh: `${levelLabel} ${required}`,
    elements: el
      ? [{ id: el.id, label_zh: el.label_zh, border: el.border }]
      : undefined,
    inspect: {
      effectTags: inspect?.effects || [],
      realmReqZh: inspect?.realm_req_zh || '无',
    },
    helpZh: inspect?.help_zh || recipe.effect_zh || undefined,
  }
}
