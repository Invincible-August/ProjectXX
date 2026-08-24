/**
 * 功法 API 类型。
 */

export interface TechniqueElementChip {
  id: string
  label_zh: string
  border: string
}

export interface TechniqueSkillChip {
  id: string
  label_zh: string
  effect_zh: string
}

export interface TechniqueItem {
  id: string
  name: string
  track: string
  level: number
  max_level: number
  next_cost?: number | null
  cost_next?: number | null
  source?: string
  source_label_zh?: string
  elements?: TechniqueElementChip[]
  help_zh?: string
  skills_main?: TechniqueSkillChip[]
  skills_art?: TechniqueSkillChip[]
}

export interface TechniqueSlotView {
  slot_type: 'main' | 'art' | string
  slot_index: number
  label_zh?: string
  technique_id: string | null
  name?: string
  level?: number
  max_level?: number
  source?: string
  source_label_zh?: string
  elements?: TechniqueElementChip[]
  help_zh?: string
}

export interface TechniqueLoadout {
  slots: TechniqueSlotView[]
  art_slot_cap: number
  main_slots: number
  help_zh?: string
  granted_skills: TechniqueSkillChip[]
}

export interface TechniquesMeData {
  items: TechniqueItem[]
  loadout?: TechniqueLoadout
}

export interface TechniqueEquipRequest {
  technique_id: string
  slot_type: 'main' | 'art'
  slot_index: number
  actor?: 'main' | 'avatar'
}

export interface TechniqueUnequipRequest {
  slot_type: 'main' | 'art'
  slot_index: number
  actor?: 'main' | 'avatar'
}
