/**
 * M7 L4 聊天 / 队伍 HTTP API。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  ChatChannelsPayload,
  ChatHistoryPayload,
  ChatMessageItem,
  PartyInviteItem,
  PartyMePayload,
  PartyPayload,
} from '../types/chat'

/** GET /chat/channels */
export async function fetchChatChannels(): Promise<ApiResponse<ChatChannelsPayload>> {
  try {
    const response = await http.get<ApiResponse<ChatChannelsPayload>>('/chat/channels')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<ChatChannelsPayload>(error)
  }
}

/** GET /chat/history */
export async function fetchChatHistory(params: {
  channel_ref: string
  limit?: number
  before_id?: number
}): Promise<ApiResponse<ChatHistoryPayload>> {
  try {
    const response = await http.get<ApiResponse<ChatHistoryPayload>>('/chat/history', {
      params,
    })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<ChatHistoryPayload>(error)
  }
}

/** POST /chat/send */
export async function sendChatMessage(body: {
  channel_type: string
  body_zh: string
  channel_ref?: string | null
  peer_character_id?: number | null
  peer_name?: string | null
}): Promise<ApiResponse<{ message: ChatMessageItem; channel_ref: string; room_id: string }>> {
  try {
    const response = await http.post<
      ApiResponse<{ message: ChatMessageItem; channel_ref: string; room_id: string }>
    >('/chat/send', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /chat/read */
export async function markChatRead(channel_ref: string): Promise<
  ApiResponse<{ channel_ref: string; unread: number; unread_total: number }>
> {
  try {
    const response = await http.post<
      ApiResponse<{ channel_ref: string; unread: number; unread_total: number }>
    >('/chat/read', { channel_ref })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /chat/dm/clear */
export async function clearDmChat(body: {
  channel_ref?: string | null
  peer_character_id?: number | null
  peer_name?: string | null
}): Promise<
  ApiResponse<{
    message?: string
    channel_ref?: string
    unread_total?: number
    dm_unread_peers?: number
  }>
> {
  try {
    const response = await http.post<
      ApiResponse<{
        message?: string
        channel_ref?: string
        unread_total?: number
        dm_unread_peers?: number
      }>
    >('/chat/dm/clear', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /party/me */
export async function fetchPartyMe(): Promise<ApiResponse<PartyMePayload>> {
  try {
    const response = await http.get<ApiResponse<PartyMePayload>>('/party/me')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /party/invite-options */
export async function fetchPartyInviteOptions(): Promise<
  ApiResponse<import('../types/chat').PartyInviteOptionsPayload>
> {
  try {
    const response = await http.get('/party/invite-options')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /party */
export async function partyAction(body: {
  action: 'create' | 'invite' | 'accept' | 'reject' | 'leave' | 'kick' | 'convert_to_team' | 'convert_to_party'
  peer_name?: string | null
  peer_character_id?: number | null
  invite_id?: number | null
}): Promise<
  ApiResponse<{
    message?: string
    party?: PartyPayload | null
    invite?: PartyInviteItem | null
    pending_invites?: PartyInviteItem[]
    outgoing_invites?: PartyInviteItem[]
  }>
> {
  try {
    const response = await http.post<
      ApiResponse<{
        message?: string
        party?: PartyPayload | null
        invite?: PartyInviteItem | null
        pending_invites?: PartyInviteItem[]
        outgoing_invites?: PartyInviteItem[]
      }>
    >('/party', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}
