/**
 * 体质 API 类型（对齐后端 constitution_service 响应）。
 */

export interface ConstitutionBag {
  id: number
  def_id: string
  name: string
  kind: string
  quality?: string
  grade?: string
  is_equipped: boolean
}

export interface ConstitutionSlotView {
  slot_type: 'main' | 'sub' | string
  slot_index: number
  item_id: number | null
}

export interface ConstitutionState {
  backpack: ConstitutionBag[]
  slots: ConstitutionSlotView[]
  equipped_summary: Array<{
    slot_type: string
    slot_index: number
    def_id: string
    name: string
  }>
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
