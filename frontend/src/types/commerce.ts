/**
 * M7 L8 商业化类型。
 */

export interface MembershipPublic {
  tier: string
  label_zh?: string
  expires_at?: string | null
  idle_cap_hours: number
}

export interface CommerceShopItem {
  item_id: string
  label_zh: string
  kind: string
  tiandao_cost?: number
  membership_tier?: string
  spirit_stones_grant?: number
  enabled?: boolean
}

export interface CommerceShopPayload {
  boundary_zh: string
  forbidden_item_types?: string[]
  items: CommerceShopItem[]
  membership: MembershipPublic
  tiandao_points: number
}

export interface CommerceMePayload {
  membership: MembershipPublic
  tiandao_points: number
  boundary_zh?: string
  currencies?: Array<Record<string, unknown>>
}
