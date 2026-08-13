/**
 * M7 L2 道友 HTTP API：list / apply / accept / reject / privacy / profile。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  FriendActionResult,
  FriendApplyResult,
  FriendListPayload,
  FriendPrivacyPayload,
  FriendProfileCard,
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

/** POST /friends — 按道号或角色 id 申请。 */
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

/** POST /friends/{id}/accept */
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

/** POST /friends/{id}/reject */
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

/** DELETE /friends/{id} */
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

/** GET /friends/privacy */
export async function fetchFriendPrivacy(): Promise<
  ApiResponse<FriendPrivacyPayload>
> {
  try {
    const response = await http.get<ApiResponse<FriendPrivacyPayload>>(
      '/friends/privacy',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FriendPrivacyPayload>(error)
  }
}

/** PUT /friends/privacy */
export async function updateFriendPrivacy(
  friendProfileVisible: boolean,
): Promise<ApiResponse<FriendPrivacyPayload>> {
  try {
    const response = await http.put<ApiResponse<FriendPrivacyPayload>>(
      '/friends/privacy',
      { friend_profile_visible: friendProfileVisible },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FriendPrivacyPayload>(error)
  }
}

/** GET /friends/profile/{characterId} */
export async function fetchFriendProfile(
  characterId: number,
): Promise<ApiResponse<FriendProfileCard>> {
  try {
    const response = await http.get<ApiResponse<FriendProfileCard>>(
      `/friends/profile/${characterId}`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FriendProfileCard>(error)
  }
}
