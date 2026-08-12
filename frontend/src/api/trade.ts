/**
 * M7 L2 交易 HTTP API：listings / auctions / face。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  AuctionListPayload,
  AuctionMutationResult,
  FaceMutationResult,
  ListingListPayload,
  ListingMutationResult,
  TradeItemLine,
} from '../types/trade'

/** GET /trade/listings */
export async function listListings(): Promise<ApiResponse<ListingListPayload>> {
  try {
    const response =
      await http.get<ApiResponse<ListingListPayload>>('/trade/listings')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<ListingListPayload>(error)
  }
}

/**
 * POST /trade/listings — 上架一口价或易物。
 *
 * @param body - mode / offer_items / price / ask_items
 */
export async function createListing(body: {
  mode?: string
  offer_items: TradeItemLine[]
  price_spirit_stones?: number
  ask_items?: TradeItemLine[]
}): Promise<ApiResponse<ListingMutationResult>> {
  try {
    const response = await http.post<ApiResponse<ListingMutationResult>>(
      '/trade/listings',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<ListingMutationResult>(error)
  }
}

/**
 * POST /trade/listings/{id}/buy
 *
 * @param listingId - 挂单 id
 */
export async function buyListing(
  listingId: number,
): Promise<ApiResponse<ListingMutationResult>> {
  try {
    const response = await http.post<ApiResponse<ListingMutationResult>>(
      `/trade/listings/${listingId}/buy`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<ListingMutationResult>(error)
  }
}

/**
 * POST /trade/listings/{id}/cancel
 *
 * @param listingId - 挂单 id
 */
export async function cancelListing(
  listingId: number,
): Promise<ApiResponse<ListingMutationResult>> {
  try {
    const response = await http.post<ApiResponse<ListingMutationResult>>(
      `/trade/listings/${listingId}/cancel`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<ListingMutationResult>(error)
  }
}

/** GET /trade/auctions */
export async function listAuctions(): Promise<ApiResponse<AuctionListPayload>> {
  try {
    const response =
      await http.get<ApiResponse<AuctionListPayload>>('/trade/auctions')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<AuctionListPayload>(error)
  }
}

/**
 * POST /trade/auctions — 上架拍品。
 *
 * @param body - offer_items / start_price / duration_sec
 */
export async function createAuction(body: {
  offer_items: TradeItemLine[]
  start_price: number
  duration_sec?: number | null
}): Promise<ApiResponse<AuctionMutationResult>> {
  try {
    const response = await http.post<ApiResponse<AuctionMutationResult>>(
      '/trade/auctions',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<AuctionMutationResult>(error)
  }
}

/**
 * POST /trade/auctions/{id}/bid
 *
 * @param lotId - 拍品 id
 * @param body - amount 灵石
 */
export async function bidAuction(
  lotId: number,
  body: { amount: number },
): Promise<ApiResponse<AuctionMutationResult>> {
  try {
    const response = await http.post<ApiResponse<AuctionMutationResult>>(
      `/trade/auctions/${lotId}/bid`,
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<AuctionMutationResult>(error)
  }
}

/**
 * POST /trade/face — 发起面交。
 *
 * @param body - peer_name 与 peer_character_id 二选一
 */
export async function faceInvite(body: {
  peer_name?: string | null
  peer_character_id?: number | null
}): Promise<ApiResponse<FaceMutationResult>> {
  try {
    const response = await http.post<ApiResponse<FaceMutationResult>>(
      '/trade/face',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FaceMutationResult>(error)
  }
}

/**
 * GET /trade/face/{id}
 *
 * @param sessionId - 面交会话 id
 */
export async function faceGet(
  sessionId: number,
): Promise<ApiResponse<FaceMutationResult>> {
  try {
    const response = await http.get<ApiResponse<FaceMutationResult>>(
      `/trade/face/${sessionId}`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FaceMutationResult>(error)
  }
}

/**
 * POST /trade/face/{id}/offer — 更新己方草稿报价（不托管）。
 *
 * @param sessionId - 会话 id
 * @param body - items / spirit_stones / version
 */
export async function faceOffer(
  sessionId: number,
  body: {
    items: TradeItemLine[]
    spirit_stones: number
    version: number
  },
): Promise<ApiResponse<FaceMutationResult>> {
  try {
    const response = await http.post<ApiResponse<FaceMutationResult>>(
      `/trade/face/${sessionId}/offer`,
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FaceMutationResult>(error)
  }
}

/**
 * POST /trade/face/{id}/accept — 受邀方接受。
 *
 * @param sessionId - 会话 id
 */
export async function faceAccept(
  sessionId: number,
): Promise<ApiResponse<FaceMutationResult>> {
  try {
    const response = await http.post<ApiResponse<FaceMutationResult>>(
      `/trade/face/${sessionId}/accept`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FaceMutationResult>(error)
  }
}

/**
 * POST /trade/face/{id}/reject — 受邀方拒绝。
 *
 * @param sessionId - 会话 id
 */
export async function faceReject(
  sessionId: number,
): Promise<ApiResponse<FaceMutationResult>> {
  try {
    const response = await http.post<ApiResponse<FaceMutationResult>>(
      `/trade/face/${sessionId}/reject`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FaceMutationResult>(error)
  }
}

/**
 * POST /trade/face/{id}/lock — 锁定并托管己方报价。
 *
 * @param sessionId - 会话 id
 * @param body - version
 */
export async function faceLock(
  sessionId: number,
  body: { version: number },
): Promise<ApiResponse<FaceMutationResult>> {
  try {
    const response = await http.post<ApiResponse<FaceMutationResult>>(
      `/trade/face/${sessionId}/lock`,
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FaceMutationResult>(error)
  }
}

/**
 * POST /trade/face/{id}/confirm
 *
 * @param sessionId - 会话 id
 * @param body - version
 */
export async function faceConfirm(
  sessionId: number,
  body: { version: number },
): Promise<ApiResponse<FaceMutationResult>> {
  try {
    const response = await http.post<ApiResponse<FaceMutationResult>>(
      `/trade/face/${sessionId}/confirm`,
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FaceMutationResult>(error)
  }
}

/**
 * POST /trade/face/{id}/cancel
 *
 * @param sessionId - 会话 id
 */
export async function faceCancel(
  sessionId: number,
): Promise<ApiResponse<FaceMutationResult>> {
  try {
    const response = await http.post<ApiResponse<FaceMutationResult>>(
      `/trade/face/${sessionId}/cancel`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FaceMutationResult>(error)
  }
}
