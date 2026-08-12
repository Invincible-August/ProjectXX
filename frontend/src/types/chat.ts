/**
 * M7 L4 聊天领域类型。
 */

export type ChatChannelType = 'world' | 'sect' | 'dm' | 'mentor' | 'party'

export interface ChatChannelItem {
  channel_type: ChatChannelType | string
  channel_ref: string | null
  label_zh: string
  can_access: boolean
  can_send: boolean
  lock_reason_zh?: string | null
  unread: number
  room_id: string | null
  peer_character_id?: number | null
  peer_name?: string | null
  party_id?: number | null
}

export interface ChatMessageItem {
  id: number
  channel_type: string
  channel_ref: string
  sender_character_id: number
  sender_name: string
  /** 发言者大境界 key，用于道号上色 */
  sender_major_realm?: string | null
  sender_major_realm_name?: string | null
  body_zh: string
  created_at: string | null
}

export interface ChatChannelsPayload {
  items: ChatChannelItem[]
  unread_total: number
  /** 有未读私聊的对方人数（按人头，非消息条数） */
  dm_unread_peers?: number
  channel_types: string[]
  /** 会话级：不拉历史；退出/关浏览器清空本端消息 */
  session_ephemeral?: boolean
}

export interface ChatHistoryPayload {
  channel_ref: string
  room_id: string
  items: ChatMessageItem[]
}

export interface PartyMemberItem {
  character_id: number
  name: string
  is_leader: boolean
  major_realm?: string | null
  major_realm_name?: string | null
  status?: string | null
  status_name?: string | null
  online?: boolean
  cultivation_points?: number
  base_atk?: number
  base_hp?: number
  technique_summary?: Array<{
    id?: string | number
    name?: string
    level?: number
    max_level?: number
  }>
  constitution_equipped?: string[]
}

export interface PartyPayload {
  id: number
  status: string
  leader_character_id: number
  members: PartyMemberItem[]
  channel_ref: string
  room_id: string
}

/** Incoming / serialized party invite */
export interface PartyInviteItem {
  id: number
  inviter_id: number
  inviter_name: string
  invitee_id: number
  invitee_name?: string
  party_id: number | null
  status: string
  expires_at: string | null
  created_at: string | null
}

export interface PartyMePayload {
  party: PartyPayload | null
  pending_invites: PartyInviteItem[]
}
