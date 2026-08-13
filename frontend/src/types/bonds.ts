/**
 * 道侣 / 炉鼎类型。
 */

export interface BondItem {
  bond_id: number
  bond_kind: 'companion' | 'vessel' | string
  peer_character_id: number
  peer_name: string
  status: string
  is_requester: boolean
  owner_character_id?: number | null
  /** 炉鼎到期 UTC ISO；道侣无 */
  expires_at?: string | null
  peer_major_realm?: string | null
  peer_major_realm_name?: string | null
  peer_cultivation_points?: number
  online?: boolean
}

export interface BondListPayload {
  companions: BondItem[]
  vessels: BondItem[]
  /** 我是别人的炉鼎时唯一主人；否则 null */
  my_master?: BondItem | null
  companion_incoming: BondItem[]
  companion_outgoing: BondItem[]
  companion_count: number
  vessel_count: number
  max_companions: number
  max_vessels: number
  vessel_invite_enabled: boolean
  vessel_hint_zh?: string
}
