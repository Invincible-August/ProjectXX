/**
 * M7 L2 交易行 / 拍卖 / 面交领域类型（对齐 TradeService）。
 */

import type { CharacterPublic } from './character'

/** 物品行（上架 / 报价） */
export interface TradeItemLine {
  item_id: string
  quantity: number
}

/** 交易行挂单 */
export interface Listing {
  id: number
  /** fixed_price | barter */
  mode: string
  mode_label_zh: string
  seller_character_id: number
  seller_name: string
  offer_items: TradeItemLine[]
  price_spirit_stones: number
  ask_items: TradeItemLine[]
  /** open | sold | cancelled */
  status: string
  fee_paid: number
}

/** GET /trade/listings */
export interface ListingListPayload {
  items: Listing[]
}

/** 上架 / 购买 / 撤单结果 */
export interface ListingMutationResult {
  message?: string
  listing?: Listing
  character?: CharacterPublic
}

/** 拍卖拍品 */
export interface AuctionLot {
  id: number
  seller_character_id: number
  seller_name: string
  offer_items: TradeItemLine[]
  start_price: number
  current_price: number
  current_bidder_id: number | null
  /** open | sold | unsold */
  status: string
  ends_at: string | null
}

/** GET /trade/auctions */
export interface AuctionListPayload {
  items: AuctionLot[]
}

/** 上架拍卖 / 出价结果 */
export interface AuctionMutationResult {
  message?: string
  lot?: AuctionLot
  character?: CharacterPublic
}

/** 面交单侧报价 */
export interface FaceOffer {
  items: TradeItemLine[]
  spirit_stones: number
}

/** 面交会话 */
export interface FaceSession {
  id: number
  /**
   * pending_invite | browsing | locking | confirming |
   * committed | cancelled | expired
   */
  status: string
  status_label_zh: string
  /** 乐观锁版本；改草稿 / 锁定 / 确认须携带 */
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
  /** 当前视角：initiator | peer */
  you_are: string
  /** 对方是否在线（WsHub / 开发假定） */
  peer_online: boolean
  expires_at: string | null
}

/** 面交 invite / get / offer / lock / confirm / cancel 结果 */
export interface FaceMutationResult {
  message?: string
  session?: FaceSession
  character?: CharacterPublic
}

/** NPC 坊市货架行 */
export interface BazaarItem {
  item_id: string
  label_zh: string
  item_type: string
  buy_price: number
  sell_price: number
  owned: number
}

/** GET /trade/bazaar */
export interface BazaarCatalogPayload {
  label_zh: string
  hint_zh: string
  max_qty_per_deal: number
  items: BazaarItem[]
  inventory_sellable: BazaarItem[]
  spirit_stones: number
}

/** POST /trade/bazaar/buy|sell */
export interface BazaarDealResult {
  item_id: string
  quantity: number
  spirit_stones_spent?: number
  spirit_stones_gained?: number
  spirit_stones: number
  message?: string
  catalog?: BazaarCatalogPayload
}
