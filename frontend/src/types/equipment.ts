/**
 * Equipment types (M8 R0 · 17-zone pointer slots + puppet loadout).
 * Slot ids align with backend app.constants.equipment; labels come from slot_label_zh.
 */
export type EquipmentSlot =
  | 'weapon_1'
  | 'weapon_2'
  | 'armor_head'
  | 'armor_chest'
  | 'armor_legs'
  | 'armor_shoes'
  | 'armor_hands'
  | 'accessory_1'
  | 'accessory_2'
  | 'ring_1'
  | 'ring_2'
  | 'fabao_1'
  | 'fabao_2'
  | 'natal_fabao'
  | 'fubao'
  | 'pet'

export interface EquipmentStatPreview {
  label_zh: string
  value: number
}

export interface EquipmentSlotPublic {
  slot: EquipmentSlot
  slot_label_zh: string
  item_uid: string | null
  item_id: string | null
  item_label_zh: string | null
  stats_preview: Record<string, EquipmentStatPreview>
  channel_enabled: boolean
  channel_label_zh: string
  occupancy?: 'equipped' | 'deployed' | string
}

export interface BagEquipmentItem {
  item_uid: string
  item_id: string
  name: string
  slot_hint: string | null
  compatible_slots?: string[]
  stats_preview?: Record<string, EquipmentStatPreview>
  quantity: number
  item_type?: string
}

export interface PuppetLoadoutEntry {
  inventory_item_id: number
  item_uid: string
  item_id: string
  label_zh: string
  occupancy: string
  divine_sense_cost?: number
  counts_toward_load?: boolean
}

export interface PuppetSenseBand {
  max_load_ratio: number | null
  combat_stat_mult: number
  zone: string
  zone_label_zh: string
}

export interface PuppetSensePublic {
  load: number
  capacity: number
  soft_cap: number
  hard_cap: number
  percent: number
  overload_mult: number
  zone: string
  zone_label_zh: string
  default_cost: number
  max_count?: number
  help_zh: string
  bands: PuppetSenseBand[]
}

export interface EquipmentChannelsPublic {
  combat_equipment: { enabled: boolean; label_zh: string }
  idle_equipment: { enabled: boolean; label_zh: string }
  dice_equipment: { enabled: boolean; label_zh: string }
}

export interface AvatarDeployPublic {
  has_avatar: boolean
  deployed: boolean
  name: string | null
  cost: number
  status?: string
  help_zh: string
}

export interface TalismanLoadoutEntry {
  inventory_item_id: number
  item_uid?: string | null
  item_id: string
  label_zh: string
  effect_id?: string | null
  quantity?: number
  occupancy?: string
}

export interface EquipmentState {
  slots: EquipmentSlotPublic[]
  bag_equipment: BagEquipmentItem[]
  channels: EquipmentChannelsPublic
  puppet_loadout?: PuppetLoadoutEntry[]
  bag_puppets?: PuppetLoadoutEntry[]
  puppet_loadout_note_zh?: string
  puppet_sense?: PuppetSensePublic
  avatar_deploy?: AvatarDeployPublic
  talisman_loadout?: TalismanLoadoutEntry[]
  bag_talismans?: TalismanLoadoutEntry[]
  talisman_loadout_note_zh?: string
  max_slots?: number
}

export interface EquipmentEquipRequest {
  slot: EquipmentSlot
  item_uid: string
  actor?: 'main' | 'avatar'
}

export interface EquipmentUnequipRequest {
  slot: EquipmentSlot
  actor?: 'main' | 'avatar'
}

export interface PuppetLoadoutRequest {
  item_uid: string
}

export interface PuppetLoadoutReplaceRequest {
  item_uids: string[]
}

export interface AvatarDeployRequest {
  deployed: boolean
}

export interface TalismanLoadoutReplaceRequest {
  inventory_item_ids?: number[]
  item_uids?: string[]
}

export interface CombatAttrBlock {
  final: Record<string, number>
  breakdown?: Array<Record<string, unknown>>
}

export interface EquipmentEquipResponse {
  equipment: EquipmentState
  combat: CombatAttrBlock
}
