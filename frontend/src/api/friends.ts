/**
 * M7 L2 道友 HTTP API：list / apply / accept / reject。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  FriendActionResult,
  FriendApplyResult,
  FriendListPayload,
} from '../types/friends'

/** GET /friends */
export async function listFriends(): Promise<ApiResponse<FriendListPayload>> {
  try {
    const response = await http.get<ApiResponse<FriendListPayload>>('/friends')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FriendListPayload>(error)
  }
}

/**
 * POST /friends — 按道号或角色 id 申请。
 *
 * @param body - target_name 与 target_character_id 二选一
 */
export async function applyFriend(body: {
  target_name?: string | null
  target_character_id?: number | null
}): Promise<ApiResponse<FriendApplyResult>> {
  try {
    const response = await http.post<ApiResponse<FriendApplyResult>>(
      '/friends',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FriendApplyResult>(error)
  }
}

/**
 * POST /friends/{id}/accept
 *
 * @param friendshipId - 友谊行 id
 */
export async function acceptFriend(
  friendshipId: number,
): Promise<ApiResponse<FriendActionResult>> {
  try {
    const response = await http.post<ApiResponse<FriendActionResult>>(
      `/friends/${friendshipId}/accept`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FriendActionResult>(error)
  }
}

/**
 * POST /friends/{id}/reject
 *
 * @param friendshipId - 友谊行 id
 */
export async function rejectFriend(
  friendshipId: number,
): Promise<ApiResponse<FriendActionResult>> {
  try {
    const response = await http.post<ApiResponse<FriendActionResult>>(
      `/friends/${friendshipId}/reject`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FriendActionResult>(error)
  }
}

/**
 * DELETE /friends/{id} — 解除道友。
 *
 * @param friendshipId - 友谊行 id
 */
export async function removeFriend(
  friendshipId: number,
): Promise<ApiResponse<FriendActionResult>> {
  try {
    const response = await http.delete<ApiResponse<FriendActionResult>>(
      `/friends/${friendshipId}`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FriendActionResult>(error)
  }
}
