/**
 * M7 L5 机缘（聊天室红包）领域类型。
 */

export interface HeritageItemLine {
  item_id: string
  quantity: number
  /** 展示名（可选，列表摘要用） */
  name?: string | null
}

export interface HeritagePacket {
  id: number
  channel_type: string
  channel_ref: string
  room_id: string
  sender_character_id: number
  sender_name: string
  mode: 'random' | 'fixed' | string
  mode_label_zh: string
  share_count: number
  shares_claimed: number
  spirit_stones_total: number
  items: HeritageItemLine[]
  status: string
  note_zh: string
  expires_at: string | null
  created_at: string | null
  already_claimed: boolean
  can_claim: boolean
}

export interface HeritageClaimResult {
  message?: string
  claimed?: { spirit_stones: number; items: HeritageItemLine[] }
  packet?: HeritagePacket
  character?: Record<string, unknown>
}
