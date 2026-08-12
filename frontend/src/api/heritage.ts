/**
 * M7 L5 机缘（聊天室红包）HTTP API。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type { HeritageClaimResult, HeritagePacket } from '../types/heritage'

/** GET /heritage?channel_ref= */
export async function listHeritage(
  channelRef: string,
): Promise<
  ApiResponse<{
    channel_ref: string
    items: HeritagePacket[]
    session_finished_keep?: number
  }>
> {
  try {
    const response = await http.get<
      ApiResponse<{
        channel_ref: string
        items: HeritagePacket[]
        session_finished_keep?: number
      }>
    >('/heritage', { params: { channel_ref: channelRef } })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /heritage */
export async function createHeritage(body: {
  channel_ref: string
  mode: 'random' | 'fixed'
  share_count: number
  spirit_stones?: number
  items?: Array<{ item_id: string; quantity: number }>
  note_zh?: string | null
}): Promise<ApiResponse<{ message?: string; packet?: HeritagePacket; character?: Record<string, unknown> }>> {
  try {
    const response = await http.post<
      ApiResponse<{ message?: string; packet?: HeritagePacket; character?: Record<string, unknown> }>
    >('/heritage', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /heritage/{id}/claim */
export async function claimHeritage(
  packetId: number,
): Promise<ApiResponse<HeritageClaimResult>> {
  try {
    const response = await http.post<ApiResponse<HeritageClaimResult>>(
      `/heritage/${packetId}/claim`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<HeritageClaimResult>(error)
  }
}
