/**
 * M7 L2 交易行 / 拍卖 / 社交交易领域类型（对齐 TradeService）。
 */

export interface TradeItemLine {
  item_id: string
  quantity: number
}

export interface Listing {
  id: number
  mode: string
  mode_label_zh?: string
  seller_character_id: number
  seller_name: string
  offer_items: TradeItemLine[]
  price_spirit_stones: number
  ask_items: TradeItemLine[]
  status: string
  fee_paid?: number
}

export interface ListingListPayload {
  items: Listing[]
}

export interface ListingMutationResult {
  message?: string
  listing?: Listing
  character?: import('./character').CharacterPublic
}

export interface AuctionLot {
  id: number
  seller_character_id: number
  seller_name: string
  offer_items: TradeItemLine[]
  start_price: number
  current_price: number
  current_bidder_id?: number | null
  status: string
  ends_at?: string | null
}

export interface AuctionListPayload {
  items: AuctionLot[]
}

export interface AuctionMutationResult {
  message?: string
  lot?: AuctionLot
  character?: import('./character').CharacterPublic
}

/** 交易单侧报价 */
export interface FaceOffer {
  items: TradeItemLine[]
  spirit_stones: number
  vessel_offer?: { hours: number } | null
}

/** 交易炉鼎要约上下文 */
export interface FaceVesselContext {
  relation?: string | null
  are_companions?: boolean
  can_offer_become?: boolean
  can_offer_extend?: boolean
  vessel_min_hours?: number
  vessel_max_hours?: number
  [key: string]: unknown
}

/** 交易会话 */
export interface FaceSession {
  id: number
  status: string
  status_label_zh?: string
  version: number
  initiator_id: number
  initiator_name: string
  peer_id: number
  peer_name: string
  initiator_offer: FaceOffer
  peer_offer: FaceOffer
  initiator_locked: boolean
  peer_locked: boolean
  initiator_confirmed: boolean
  peer_confirmed: boolean
  you_are: 'initiator' | 'peer' | string
  peer_online?: boolean
  expires_at?: string | null
  vessel_context?: FaceVesselContext | null
}

/** 交易 invite / get / offer / lock / confirm / cancel 结果 */
export interface FaceMutationResult {
  message?: string
  session?: FaceSession
  character?: import('./character').CharacterPublic
  vessel?: Record<string, unknown> | null
}

/** 快捷选人目标 */
export interface FaceInviteTarget {
  character_id: number
  name: string
  online?: boolean
  role?: string
  role_label_zh?: string
  bond_id?: number
}

/** GET /trade/face/invite-options */
export interface FaceInviteOptions {
  friends: FaceInviteTarget[]
  companions: FaceInviteTarget[]
  sect_members: FaceInviteTarget[]
  mentors: FaceInviteTarget[]
  face_max_item_lines: number
  face_timeout_sec?: number
}

/** GET /trade/face/pending 单项 */
export interface FacePendingInvite {
  session_id: number
  from_character_id: number
  from_name: string
  status: string
  expires_at?: string | null
  invite_kind?: string
  invite_kind_label_zh?: string
}

export interface FacePendingPayload {
  items: FacePendingInvite[]
}

export interface BazaarItem {
  item_id: string
  label_zh: string
  buy_price: number
  sell_price: number
  owned: number
  item_type?: string
  name?: string
}

export interface BazaarCatalogPayload {
  label_zh?: string
  hint_zh?: string
  max_qty_per_deal?: number
  items?: BazaarItem[]
  inventory_sellable?: BazaarItem[]
  spirit_stones?: number
}

export interface BazaarDealResult {
  message?: string
  catalog?: BazaarCatalogPayload
  spirit_stones?: number
}
