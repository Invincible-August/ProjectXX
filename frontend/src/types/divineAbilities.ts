/**
 * 神通 API 类型。
 */

export interface DivineAbilityElementChip {
  id: string
  label_zh: string
  border: string
}

export interface DivineAbilityItem {
  id: string
  name: string
  source?: string
  source_label_zh?: string
  help_zh?: string
  effect_zh?: string
  elements?: DivineAbilityElementChip[]
}

export interface DivineAbilitySlotView {
  slot_index: number
  label_zh?: string
  ability_id: string | null
  name?: string
  source?: string
  source_label_zh?: string
  help_zh?: string
  effect_zh?: string
  elements?: DivineAbilityElementChip[]
}

export interface DivineAbilityLoadout {
  slots: DivineAbilitySlotView[]
  slot_cap: number
  realm_slots?: number
  grade_slots?: number
  help_zh?: string
}

export interface DivineAbilitiesMeData {
  items: DivineAbilityItem[]
  loadout?: DivineAbilityLoadout
}

export interface DivineAbilityEquipRequest {
  ability_id: string
  slot_index: number
  actor?: 'main' | 'avatar'
}

export interface DivineAbilityUnequipRequest {
  slot_index: number
  actor?: 'main' | 'avatar'
}
