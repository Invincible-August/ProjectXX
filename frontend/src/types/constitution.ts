/**
 * 体质 API 类型（对齐后端 constitution_service 响应）。
 */

export interface ConstitutionBag {
  id: number
  def_id: string
  name: string
  icon?: string | null
  kind: string
  quality?: string
  grade?: string
  is_equipped: boolean
  main_effects?: Record<string, number>
  sub_effects?: Record<string, number>
  main_effects_zh?: string
  sub_effects_zh?: string
}

export interface ConstitutionSlotView {
  slot_type: 'main' | 'sub' | string
  slot_index: number
  item_id: number | null
  label_zh?: string
  name?: string
  icon?: string | null
  active_effects_zh?: string
}

export interface ConstitutionState {
  collection: ConstitutionBag[]
  backpack: ConstitutionBag[]
  slots: ConstitutionSlotView[]
  equipped_summary: Array<{
    slot_type: string
    slot_index: number
    def_id: string
    name: string
  }>
  help_zh?: string
  soft_cap?: number
  slot_count?: number
  labels_zh?: Record<string, string>
}

export interface ConstitutionEquipRequest {
  item_id: number
  slot_type: 'main' | 'sub'
  slot_index: number
}

export interface ConstitutionUnequipRequest {
  slot_type: 'main' | 'sub'
  slot_index: number
}
