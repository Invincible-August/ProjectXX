/**
 * M7 L4 聊天 Pinia store：频道 / 会话消息 / 发送 / WS 推送 / 轮询降级。
 *
 * 非私聊默认 ``session_ephemeral``；私聊走独立弹窗并拉服务端 history。
 */
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import {
  clearDmChat,
  fetchChatChannels,
  fetchChatHistory,
  fetchPartyMe,
  markChatRead,
  partyAction,
  sendChatMessage,
} from '../api/chat'
import type {
  ChatChannelItem,
  ChatMessageItem,
  PartyInviteItem,
  PartyPayload,
} from '../types/chat'
import type { WsEnvelope } from '../types/ws'
import { isChannelJoinNotice } from '../utils/chatRealmNameColor'
import { subscribeChannel, unsubscribeChannel } from '../ws/channels'
import { WsType } from '../ws/protocol'
import { notifyInviteJump } from '../utils/inviteNotify'
import { useCharacterStore } from './character'
import { useBondsStore } from './bonds'
import { useDualCultivationStore } from './dualCultivation'
import { useFriendsStore } from './friends'
import { useGameLogStore } from './gameLog'
import { useHeritageStore } from './heritage'
import { useTradeStore } from './trade'
import { useWsStore } from './ws'

/**
 * 规范化并过滤不可展示的聊天行（如「进入频道」提示）。
 *
 * @param raw - API / WS 原始消息
 */
function normalizeChatMessage(
  raw: Partial<ChatMessageItem> & { id?: number },
): ChatMessageItem | null {
  if (!raw?.id) return null
  const bodyZh = String(raw.body_zh || '')
  if (isChannelJoinNotice(bodyZh)) return null
  return {
    id: Number(raw.id),
    channel_type: String(raw.channel_type || ''),
    channel_ref: String(raw.channel_ref || ''),
    sender_character_id: Number(raw.sender_character_id || 0),
    sender_name: String(raw.sender_name || ''),
    sender_major_realm: (raw.sender_major_realm as string | null) ?? null,
    sender_major_realm_name: (raw.sender_major_realm_name as string | null) ?? null,
    body_zh: bodyZh,
    created_at: (raw.created_at as string | null) ?? null,
  }
}

const POLL_MS = 8000

export const useChatStore = defineStore('chat', () => {
  const channels = ref<ChatChannelItem[]>([])
  const activeChannelRef = ref<string | null>(null)
  const messages = ref<ChatMessageItem[]>([])
  /** 本浏览器会话内按频道缓存的消息（关浏览器 / 登出清空） */
  const sessionMessagesByChannel = ref<Record<string, ChatMessageItem[]>>({})
  const unreadTotal = ref(0)
  /** 有未读的私聊对方人数（聊天坞主角标按此显示） */
  const dmUnreadPeers = ref(0)
  const party = ref<PartyPayload | null>(null)
  /** Incoming party invites for current character */
  const pendingInvites = ref<PartyInviteItem[]>([])
  /** Outgoing pending invites sent by current character */
  const outgoingInvites = ref<PartyInviteItem[]>([])
  /** Local waiting hint after sending an invite */
  const waitingInvite = ref<PartyInviteItem | null>(null)
  const partyLimits = ref<{
    party_max_members?: number
    team_max_members?: number
    invite_expire_sec?: number
  } | null>(null)
  const loading = ref(false)
  const lastError = ref('')
  const dockOpen = ref(false)
  const draft = ref('')
  /** 由 GET /chat/channels 下发；默认 true（仅约束非私聊坞） */
  const sessionEphemeral = ref(true)
  const dmHistoryLimit = ref(100)
  /** 独立私聊弹窗 */
  const dmDialogOpen = ref(false)
  const dmChannelRef = ref<string | null>(null)
  const dmMessages = ref<ChatMessageItem[]>([])
  const dmDraft = ref('')

  let pollTimer: number | null = null
  let wsUnsub: (() => void) | null = null
  /** 当前已订阅的全部聊天房（在线期间保持，不随页签切换退订） */
  let joinedRoomIds = new Set<string>()
  let pageHideBound = false
  /** 是否已启动「在线收信」会话 */
  const sessionListening = ref(false)

  const activeChannel = computed(
    () => channels.value.find((c) => c.channel_ref === activeChannelRef.value) ?? null,
  )

  const dmChannels = computed(() =>
    channels.value.filter((c) => c.channel_type === 'dm' && c.can_access && c.channel_ref),
  )

  const dmActiveChannel = computed(
    () => channels.value.find((c) => c.channel_ref === dmChannelRef.value) ?? null,
  )

  /**
   * 从频道列表重算私聊未读人数（兜底）。
   */
  function recountDmUnreadPeers(): number {
    return channels.value.filter(
      (c) => c.channel_type === 'dm' && Number(c.unread) > 0,
    ).length
  }

  /**
   * 同步角标：主提示用私聊人头数。
   *
   * @param total - 全频道消息未读总和（保留字段）
   * @param dmPeers - 有未读的私聊人数；缺省则本地重算
   */
  function syncBadge(total: number, dmPeers?: number): void {
    unreadTotal.value = total
    const peers =
      typeof dmPeers === 'number' && Number.isFinite(dmPeers)
        ? Math.max(0, Math.floor(dmPeers))
        : recountDmUnreadPeers()
    dmUnreadPeers.value = peers
    const ch = useCharacterStore().character
    if (!ch) return
    useCharacterStore().applyCharacter({
      ...ch,
      social_badges: {
        ...(ch.social_badges ?? {}),
        mail_unread: Number(ch.social_badges?.mail_unread ?? 0),
        // 聊天角标按私聊人头提示
        chat_unread: peers,
        dual_invite: Number(ch.social_badges?.dual_invite ?? 0),
      },
    })
  }

  /**
   * 把当前频道消息写回会话缓存。
   */
  function _persistActiveSessionMessages(): void {
    const ref = activeChannelRef.value
    if (!ref) return
    sessionMessagesByChannel.value = {
      ...sessionMessagesByChannel.value,
      [ref]: [...messages.value],
    }
  }

  /**
   * 退出登录 / 关闭浏览器：清空本会话聊天展示（不删服务端落库）。
   */
  function clearSession(): void {
    messages.value = []
    sessionMessagesByChannel.value = {}
    draft.value = ''
    lastError.value = ''
    dockOpen.value = false
    activeChannelRef.value = null
    dmDialogOpen.value = false
    dmChannelRef.value = null
    dmMessages.value = []
    dmDraft.value = ''
    party.value = null
    pendingInvites.value = []
    outgoingInvites.value = []
    waitingInvite.value = null
    partyLimits.value = null
    unreadTotal.value = 0
    dmUnreadPeers.value = 0
    sessionListening.value = false
    _clearAllSubscriptions()
    stopPollingFallback()
    useHeritageStore().clearSession()
  }

  /**
   * 监听 pagehide：关标签/关浏览器时清空会话聊天与已结束机缘本地态。
   */
  function bindPageHideClear(): void {
    if (pageHideBound || typeof window === 'undefined') return
    pageHideBound = true
    window.addEventListener('pagehide', () => {
      clearSession()
    })
  }

  async function refreshChannels(): Promise<string | null> {
    const envelope = await fetchChatChannels()
    if (envelope.code !== 0 || !envelope.data) {
      const msg = envelope.message || `加载频道失败（code=${envelope.code}）`
      lastError.value = msg
      return msg
    }
    channels.value = envelope.data.items ?? []
    if (typeof envelope.data.session_ephemeral === 'boolean') {
      sessionEphemeral.value = envelope.data.session_ephemeral
    }
    if (typeof envelope.data.dm_history_limit === 'number') {
      dmHistoryLimit.value = Math.max(1, Math.floor(envelope.data.dm_history_limit))
    }
    syncBadge(
      Number(envelope.data.unread_total ?? 0),
      typeof envelope.data.dm_unread_peers === 'number'
        ? envelope.data.dm_unread_peers
        : undefined,
    )
    // 刷新目录后订齐所有可进频道，保证后台也能收世界/宗门/私聊等
    _syncAllChannelSubscriptions()
    return null
  }

  /**
   * 进房：会话级模式下不拉历史，仅恢复本会话缓存并订阅 WS。
   *
   * @param channelRef - 频道 ref
   */
  async function enterChannelLive(channelRef: string): Promise<string | null> {
    loading.value = true
    lastError.value = ''
    try {
      // 展示本会话已缓存的该频消息（在线期间其它页签收到的也会在此）
      messages.value = [...(sessionMessagesByChannel.value[channelRef] ?? [])]
      await _syncAllChannelSubscriptions()
      await markChatRead(channelRef)
      await refreshChannels()
      // refresh 可能冲掉本地未读，但 messages 仍以会话缓存为准
      messages.value = [...(sessionMessagesByChannel.value[channelRef] ?? [])]
      return null
    } finally {
      loading.value = false
    }
  }

  async function loadHistory(channelRef: string): Promise<string | null> {
    loading.value = true
    lastError.value = ''
    try {
      const lim =
        channelRef.startsWith('dm:')
          ? dmHistoryLimit.value
          : 50
      const envelope = await fetchChatHistory({ channel_ref: channelRef, limit: lim })
      if (envelope.code !== 0 || !envelope.data) {
        messages.value = []
        const msg = envelope.message || `加载历史失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      messages.value = (envelope.data.items ?? [])
        .map((item) => normalizeChatMessage(item))
        .filter((item): item is ChatMessageItem => item != null)
      sessionMessagesByChannel.value = {
        ...sessionMessagesByChannel.value,
        [channelRef]: [...messages.value],
      }
      const roomId = envelope.data.room_id
      if (roomId) {
        // 历史模式仍订齐全频道，避免只订当前房
        void _syncAllChannelSubscriptions()
      }
      await markChatRead(channelRef)
      await refreshChannels()
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * Load DM history into the dialog list (does not disturb dock ``messages``).
   *
   * @param channelRef - dm channel_ref
   */
  async function loadDmHistory(channelRef: string): Promise<string | null> {
    loading.value = true
    lastError.value = ''
    try {
      const envelope = await fetchChatHistory({
        channel_ref: channelRef,
        limit: dmHistoryLimit.value,
      })
      if (envelope.code !== 0 || !envelope.data) {
        dmMessages.value = []
        const msg = envelope.message || `加载私聊失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      const items = (envelope.data.items ?? [])
        .map((item) => normalizeChatMessage(item))
        .filter((item): item is ChatMessageItem => item != null)
      dmMessages.value = items
      sessionMessagesByChannel.value = {
        ...sessionMessagesByChannel.value,
        [channelRef]: [...items],
      }
      void _syncAllChannelSubscriptions()
      await markChatRead(channelRef)
      await refreshChannels()
      return null
    } finally {
      loading.value = false
    }
  }

  async function selectChannel(channelRef: string | null): Promise<void> {
    _persistActiveSessionMessages()
    activeChannelRef.value = channelRef
    if (!channelRef) {
      messages.value = []
      return
    }
    // 坞内不切私聊（私聊走弹窗）；若误传 dm 则仍拉历史
    if (channelRef.startsWith('dm:') || !sessionEphemeral.value) {
      await loadHistory(channelRef)
    } else {
      await enterChannelLive(channelRef)
    }
  }

  /**
   * Select a DM thread inside the dialog and load persisted history.
   *
   * @param channelRef - dm channel_ref
   */
  async function selectDm(channelRef: string): Promise<string | null> {
    dmChannelRef.value = channelRef
    return loadDmHistory(channelRef)
  }

  async function send(bodyZh?: string): Promise<string | null> {
    const ch = activeChannel.value
    if (!ch?.channel_ref || !ch.can_send) {
      return ch?.lock_reason_zh || '当前频道不可发言'
    }
    const text = (bodyZh ?? draft.value).trim()
    if (!text) return '消息不可为空'
    loading.value = true
    try {
      const envelope = await sendChatMessage({
        channel_type: ch.channel_type,
        channel_ref: ch.channel_ref,
        body_zh: text,
        peer_character_id: ch.peer_character_id,
        peer_name: ch.peer_name,
      })
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `发送失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      draft.value = ''
      const msg = normalizeChatMessage(envelope.data.message)
      if (msg && !messages.value.some((m) => m.id === msg.id)) {
        messages.value = [...messages.value, msg]
        _persistActiveSessionMessages()
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * Refresh party + pending/outgoing invites from GET /party/me.
   */
  async function refreshPartyMe(): Promise<string | null> {
    const envelope = await fetchPartyMe()
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || `加载队伍失败（code=${envelope.code}）`
    }
    party.value = envelope.data.party ?? null
    pendingInvites.value = envelope.data.pending_invites ?? []
    outgoingInvites.value = envelope.data.outgoing_invites ?? []
    if (envelope.data.limits) {
      partyLimits.value = envelope.data.limits
    }
    if (waitingInvite.value) {
      const stillOut = outgoingInvites.value.some(
        (i) => i.id === waitingInvite.value?.id,
      )
      const members = party.value?.members ?? []
      const peerJoined = members.some(
        (m) => m.character_id === waitingInvite.value?.invitee_id,
      )
      if (peerJoined || !stillOut) {
        waitingInvite.value = null
      }
    }
    return null
  }

  /**
   * Create an empty party (no force-join peer).
   */
  async function createParty(): Promise<string | null> {
    const envelope = await partyAction({ action: 'create' })
    if (envelope.code !== 0) {
      return envelope.message || `创建队伍失败（code=${envelope.code}）`
    }
    party.value = envelope.data?.party ?? null
    pendingInvites.value = envelope.data?.pending_invites ?? pendingInvites.value
    outgoingInvites.value = envelope.data?.outgoing_invites ?? outgoingInvites.value
    await refreshChannels()
    return null
  }

  /**
   * Invite a peer by dao name (requires relation + online gate server-side).
   *
   * @param peerName - Invitee dao name
   */
  async function inviteToParty(peerName: string): Promise<string | null> {
    const name = peerName.trim()
    if (!name) return '请填写队友道号'
    const envelope = await partyAction({
      action: 'invite',
      peer_name: name,
    })
    if (envelope.code !== 0) {
      return envelope.message || `邀请失败（code=${envelope.code}）`
    }
    party.value = envelope.data?.party ?? null
    if (envelope.data?.invite) {
      waitingInvite.value = envelope.data.invite
    }
    pendingInvites.value = envelope.data?.pending_invites ?? pendingInvites.value
    outgoingInvites.value = envelope.data?.outgoing_invites ?? outgoingInvites.value
    await refreshChannels()
    return null
  }

  /**
   * Leader converts party → team (max 40).
   */
  async function convertToTeam(): Promise<string | null> {
    const envelope = await partyAction({ action: 'convert_to_team' })
    if (envelope.code !== 0) {
      return envelope.message || `转换团队失败（code=${envelope.code}）`
    }
    party.value = envelope.data?.party ?? null
    pendingInvites.value = envelope.data?.pending_invites ?? pendingInvites.value
    outgoingInvites.value = envelope.data?.outgoing_invites ?? outgoingInvites.value
    return null
  }

  /**
   * Leader converts team → party when members ≤ 5.
   */
  async function convertToParty(): Promise<string | null> {
    const envelope = await partyAction({ action: 'convert_to_party' })
    if (envelope.code !== 0) {
      return envelope.message || `转回队伍失败（code=${envelope.code}）`
    }
    party.value = envelope.data?.party ?? null
    pendingInvites.value = envelope.data?.pending_invites ?? pendingInvites.value
    outgoingInvites.value = envelope.data?.outgoing_invites ?? outgoingInvites.value
    return null
  }

  /**
   * Accept an incoming party invite.
   *
   * @param inviteId - PartyInvite id
   */
  async function acceptPartyInvite(inviteId: number): Promise<string | null> {
    const envelope = await partyAction({
      action: 'accept',
      invite_id: inviteId,
    })
    if (envelope.code !== 0) {
      return envelope.message || `接受邀请失败（code=${envelope.code}）`
    }
    party.value = envelope.data?.party ?? null
    pendingInvites.value = envelope.data?.pending_invites ?? []
    outgoingInvites.value = envelope.data?.outgoing_invites ?? []
    waitingInvite.value = null
    await refreshChannels()
    return null
  }

  /**
   * Reject an incoming party invite.
   *
   * @param inviteId - PartyInvite id
   */
  async function rejectPartyInvite(inviteId: number): Promise<string | null> {
    const envelope = await partyAction({
      action: 'reject',
      invite_id: inviteId,
    })
    if (envelope.code !== 0) {
      return envelope.message || `拒绝邀请失败（code=${envelope.code}）`
    }
    pendingInvites.value = envelope.data?.pending_invites ?? []
    outgoingInvites.value = envelope.data?.outgoing_invites ?? outgoingInvites.value
    return null
  }

  async function leaveParty(): Promise<string | null> {
    const envelope = await partyAction({ action: 'leave' })
    if (envelope.code !== 0) {
      return envelope.message || `离队失败（code=${envelope.code}）`
    }
    party.value = null
    waitingInvite.value = null
    pendingInvites.value = envelope.data?.pending_invites ?? []
    outgoingInvites.value = envelope.data?.outgoing_invites ?? []
    if (activeChannel.value?.channel_type === 'party') {
      await selectChannel(null)
      if (dockOpen.value) {
        await refreshChannels()
        await ensureWorldChannelSelected()
        return null
      }
    }
    await refreshChannels()
    return null
  }

  /**
   * Leader kicks a member by dao name or character id.
   *
   * @param opts - peer_name and/or peer_character_id
   */
  async function kickFromParty(opts: {
    peer_name?: string | null
    peer_character_id?: number | null
  }): Promise<string | null> {
    const envelope = await partyAction({
      action: 'kick',
      peer_name: opts.peer_name,
      peer_character_id: opts.peer_character_id,
    })
    if (envelope.code !== 0) {
      return envelope.message || `踢出失败（code=${envelope.code}）`
    }
    party.value = envelope.data?.party ?? null
    pendingInvites.value = envelope.data?.pending_invites ?? pendingInvites.value
    outgoingInvites.value = envelope.data?.outgoing_invites ?? outgoingInvites.value
    await refreshChannels()
    return null
  }

  function applyPush(envelope: WsEnvelope): void {
    if (envelope.type === WsType.GAME_LOG) {
      const p = (envelope.payload || {}) as {
        message?: string
        level?: string
      }
      const msg = String(p.message || '').trim()
      if (!msg) return
      const levelRaw = String(p.level || 'info')
      const level =
        levelRaw === 'success' ||
        levelRaw === 'warning' ||
        levelRaw === 'system'
          ? levelRaw
          : 'info'
      useGameLogStore().push(msg, level)
      return
    }
    if (
      envelope.type === WsType.HERITAGE_CREATED ||
      envelope.type === WsType.HERITAGE_CLAIMED ||
      envelope.type === WsType.HERITAGE_EXPIRED
    ) {
      useHeritageStore().applyPush(envelope)
      return
    }
    if (envelope.type === WsType.PRESENCE_CHANGED) {
      const p = envelope.payload as {
        character_id?: number
        online?: boolean
      }
      const cid = Number(p.character_id)
      if (!cid) return
      const online = Boolean(p.online)
      applyPartyPresence(cid, online)
      useFriendsStore().applyPresence(cid, online)
      useBondsStore().applyPresence(cid, online)
      useTradeStore().applyPresence(cid, online)
      return
    }
    if (
      envelope.type === WsType.FRIEND_REQUEST ||
      envelope.type === WsType.FRIEND_UPDATE
    ) {
      useFriendsStore().applyPush(envelope)
      return
    }
    if (
      envelope.type === WsType.BOND_REQUEST ||
      envelope.type === WsType.BOND_UPDATE
    ) {
      useBondsStore().applyPush(envelope)
      return
    }
    if (
      envelope.type === WsType.DUAL_INVITE ||
      envelope.type === WsType.DUAL_UPDATE
    ) {
      useDualCultivationStore().applyPush(envelope)
      return
    }
    if (
      envelope.type === WsType.FACE_INVITE ||
      envelope.type === WsType.FACE_UPDATE
    ) {
      useTradeStore().applyPush(envelope)
      return
    }
    if (
      envelope.type === WsType.PARTY_INVITE ||
      envelope.type === WsType.PARTY_UPDATE
    ) {
      const p = (envelope.payload || {}) as {
        event?: string
        message?: string
        id?: number
        inviter_name?: string
        invite?: { id?: number; inviter_name?: string }
      }
      const event = String(p.event || '')
      // party.invite 已弹过；party.update event=invite 是同一次邀请的重复推送，不再弹
      const isInviteType = envelope.type === WsType.PARTY_INVITE
      const inviteId = Number(p.id || p.invite?.id || 0)
      const inviterName =
        String(p.inviter_name || p.invite?.inviter_name || '').trim() || '道友'

      if (isInviteType) {
        notifyInviteJump({
          title: '组队邀请',
          message:
            String(p.message || '').trim() ||
            `「${inviterName}」邀请你加入队伍`,
          type: 'info',
          dedupeKey: inviteId > 0 ? `party:invite:${inviteId}` : undefined,
          to: { path: '/social', query: { mode: 'party' } },
          afterNavigate: () => {
            void refreshPartyMe()
            void refreshChannels()
          },
        })
      } else if (
        event === 'accepted' ||
        event === 'rejected' ||
        event === 'kicked' ||
        event === 'left' ||
        event === 'disbanded'
      ) {
        const title =
          event === 'accepted'
            ? '入队成功'
            : event === 'rejected'
              ? '入队拒绝'
              : '队伍通知'
        const msg =
          String(p.message || '').trim() ||
          (event === 'accepted'
            ? '组队邀请已接受'
            : event === 'rejected'
              ? '组队邀请已拒绝'
              : '队伍成员变动')
        const nType =
          event === 'accepted'
            ? 'success'
            : event === 'rejected' || event === 'kicked'
              ? 'warning'
              : 'info'
        notifyInviteJump({
          title,
          message: msg,
          type: nType,
          dedupeKey: inviteId > 0 ? `party:${event}:${inviteId}` : `party:${event}`,
          to: { path: '/social', query: { mode: 'party' } },
          afterNavigate: () => {
            void refreshPartyMe()
            void refreshChannels()
          },
        })
      }
      void refreshPartyMe()
      void refreshChannels()
      return
    }
    if (envelope.type === WsType.CHAT_MESSAGE) {
      const p = envelope.payload as Partial<ChatMessageItem>
      if (!p?.id || !p.channel_ref) return
      const channelRef = String(p.channel_ref)
      const msg = normalizeChatMessage(p)
      if (!msg) return
      // 写入对应频道会话缓存（即便坞未开 / 当前不在该频）
      const cached = sessionMessagesByChannel.value[channelRef] ?? []
      if (!cached.some((m) => m.id === msg.id)) {
        sessionMessagesByChannel.value = {
          ...sessionMessagesByChannel.value,
          [channelRef]: [...cached, msg],
        }
      }
      // 当前正在看该频：同步进可见列表
      if (channelRef === activeChannelRef.value) {
        if (!messages.value.some((m) => m.id === msg.id)) {
          messages.value = [...messages.value, msg]
        }
      }
      // 私聊弹窗当前会话
      if (channelRef === dmChannelRef.value) {
        if (!dmMessages.value.some((m) => m.id === msg.id)) {
          dmMessages.value = [...dmMessages.value, msg]
        }
      }
      return
    }
    if (envelope.type === WsType.CHAT_DM_CLEARED) {
      const p = envelope.payload as { channel_ref?: string }
      const cref = String(p.channel_ref || '')
      if (!cref) return
      const nextCache = { ...sessionMessagesByChannel.value }
      delete nextCache[cref]
      sessionMessagesByChannel.value = nextCache
      if (dmChannelRef.value === cref) {
        dmMessages.value = []
      }
      void refreshChannels()
      return
    }
    if (envelope.type === WsType.CHAT_UNREAD) {
      const payload = envelope.payload as {
        unread_total?: number
        dm_unread_peers?: number
      }
      const total = Number(payload.unread_total ?? 0)
      syncBadge(
        total,
        typeof payload.dm_unread_peers === 'number'
          ? payload.dm_unread_peers
          : undefined,
      )
      void refreshChannels()
    }
  }

  /**
   * Hot-update party member online dots from presence push.
   *
   * @param characterId - Member character id
   * @param online - New flag
   */
  function applyPartyPresence(characterId: number, online: boolean): void {
    const p = party.value
    if (!p?.members?.length) return
    const cid = Number(characterId)
    const nextMembers = p.members.map((m) =>
      Number(m.character_id) === cid ? { ...m, online } : m,
    )
    party.value = { ...p, members: nextMembers }
  }

  function startPollingFallback(): void {
    stopPollingFallback()
    const ws = useWsStore()
    pollTimer = window.setInterval(() => {
      if (!dockOpen.value || !activeChannelRef.value) return
      if (ws.status === 'open') return
      // 会话级模式：断线时不拉全量历史，避免「清空」被历史填回
      if (sessionEphemeral.value) return
      void loadHistory(activeChannelRef.value)
    }, POLL_MS)
  }

  function stopPollingFallback(): void {
    if (pollTimer != null) {
      window.clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function ensureWsHandler(): void {
    if (wsUnsub) return
    wsUnsub = useWsStore().subscribe((e) => applyPush(e))
  }

  /**
   * 玩法壳在线即开始收信：挂 WS 处理 + 拉频道 + 订齐所有可进房。
   * 已在听时仅确保订阅，不重复全量刷新（壳内切页可重复调用）。
   */
  async function startSessionListening(): Promise<void> {
    bindPageHideClear()
    ensureWsHandler()
    if (sessionListening.value) {
      _syncAllChannelSubscriptions()
      return
    }
    sessionListening.value = true
    const err = await refreshChannels()
    if (err) {
      lastError.value = err
      return
    }
    await refreshPartyMe()
    _syncAllChannelSubscriptions()
  }

  /**
   * 打开聊天坞：默认进世界频；收信已由 startSessionListening 保证。
   */
  async function openDock(): Promise<void> {
    await startSessionListening()
    dockOpen.value = true
    startPollingFallback()
    await ensureWorldChannelSelected()
  }

  /**
   * 若当前未选频道，自动选中可进入的世界频道。
   */
  async function ensureWorldChannelSelected(): Promise<void> {
    // 坞不再承载私聊：若当前误留在 dm，改回世界频
    if (activeChannelRef.value?.startsWith('dm:')) {
      activeChannelRef.value = null
    }
    if (activeChannelRef.value) {
      const stillOk = channels.value.some(
        (c) =>
          c.channel_ref === activeChannelRef.value &&
          c.can_access &&
          c.channel_type !== 'dm' &&
          Boolean(c.channel_ref),
      )
      if (stillOk) {
        const ref = activeChannelRef.value
        messages.value = [...(sessionMessagesByChannel.value[ref] ?? [])]
        return
      }
    }
    const world = channels.value.find(
      (c) =>
        c.channel_type === 'world' && c.can_access && Boolean(c.channel_ref),
    )
    if (world?.channel_ref) {
      await selectChannel(world.channel_ref)
    }
  }

  /**
   * 打开独立私聊弹窗；可选预选道友。
   *
   * @param peerCharacterId - 对方角色 id
   */
  async function openDmDialog(peerCharacterId?: number | null): Promise<string | null> {
    await startSessionListening()
    await refreshChannels()
    dmDialogOpen.value = true
    const peerId = Number(peerCharacterId || 0)
    if (!peerId) {
      // 无指定时：优先第一个有未读，否则第一个会话
      const unread = dmChannels.value.find((c) => Number(c.unread) > 0)
      const first = unread || dmChannels.value[0]
      if (first?.channel_ref) {
        return selectDm(first.channel_ref)
      }
      return null
    }
    const dm = dmChannels.value.find((c) => {
      if (Number(c.peer_character_id) === peerId) return true
      const parts = String(c.channel_ref || '').split(':')
      return parts[0] === 'dm' && parts.slice(1).map(Number).includes(peerId)
    })
    if (!dm?.channel_ref) {
      return '尚未生成私聊频道，请确认已结为道友后重试'
    }
    return selectDm(dm.channel_ref)
  }

  function closeDmDialog(): void {
    dmDialogOpen.value = false
  }

  /**
   * @deprecated 兼容旧调用：改为打开私聊弹窗
   */
  async function openDm(peerCharacterId: number): Promise<string | null> {
    return openDmDialog(peerCharacterId)
  }

  /**
   * Send in the active DM dialog thread.
   */
  async function sendDm(bodyZh?: string): Promise<string | null> {
    const ch = dmActiveChannel.value
    if (!ch?.channel_ref || !ch.can_send) {
      return ch?.lock_reason_zh || '当前私聊不可发言'
    }
    const text = (bodyZh ?? dmDraft.value).trim()
    if (!text) return '消息不可为空'
    loading.value = true
    try {
      const envelope = await sendChatMessage({
        channel_type: 'dm',
        channel_ref: ch.channel_ref,
        body_zh: text,
        peer_character_id: ch.peer_character_id,
        peer_name: ch.peer_name,
      })
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `发送失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      dmDraft.value = ''
      const msg = normalizeChatMessage(envelope.data.message)
      if (msg) {
        if (!dmMessages.value.some((m) => m.id === msg.id)) {
          dmMessages.value = [...dmMessages.value, msg]
        }
        const cref = ch.channel_ref
        const cached = sessionMessagesByChannel.value[cref] ?? []
        if (!cached.some((m) => m.id === msg.id)) {
          sessionMessagesByChannel.value = {
            ...sessionMessagesByChannel.value,
            [cref]: [...cached, msg],
          }
        }
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * Clear current DM thread on server and locally.
   */
  async function clearDm(): Promise<string | null> {
    const cref = dmChannelRef.value
    if (!cref) return '未选择私聊会话'
    loading.value = true
    try {
      const envelope = await clearDmChat({ channel_ref: cref })
      if (envelope.code !== 0) {
        const msg = envelope.message || `清空失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      dmMessages.value = []
      const nextCache = { ...sessionMessagesByChannel.value }
      delete nextCache[cref]
      sessionMessagesByChannel.value = nextCache
      if (typeof envelope.data?.dm_unread_peers === 'number') {
        syncBadge(
          Number(envelope.data.unread_total ?? unreadTotal.value),
          envelope.data.dm_unread_peers,
        )
      }
      await refreshChannels()
      return null
    } finally {
      loading.value = false
    }
  }

  function closeDock(): void {
    _persistActiveSessionMessages()
    dockOpen.value = false
    // 关坞不停收信：会话缓存与订阅保持，直到登出/关浏览器
  }

  /**
   * 订阅全部可访问聊天房；切页签不退订，保证后台收齐各频消息。
   */
  function _syncAllChannelSubscriptions(): void {
    const client = useWsStore().client
    const wanted = new Set<string>()
    for (const ch of channels.value) {
      if (!ch.can_access || !ch.room_id) continue
      const rid = String(ch.room_id).trim()
      if (rid) wanted.add(rid)
    }
    for (const rid of [...joinedRoomIds]) {
      if (!wanted.has(rid)) {
        unsubscribeChannel(client, rid)
        joinedRoomIds.delete(rid)
      }
    }
    if (useWsStore().status !== 'open') return
    for (const rid of wanted) {
      if (joinedRoomIds.has(rid)) continue
      if (subscribeChannel(client, rid)) {
        joinedRoomIds.add(rid)
      }
    }
  }

  function _clearAllSubscriptions(): void {
    const client = useWsStore().client
    for (const rid of [...joinedRoomIds]) {
      unsubscribeChannel(client, rid)
    }
    joinedRoomIds.clear()
  }

  watch(
    () => useWsStore().status,
    (st) => {
      // 套接字失效后本地 joined 作废，必须在重连 open 后重新 room.join
      if (st !== 'open') {
        joinedRoomIds.clear()
        return
      }
      if (!sessionListening.value && !dockOpen.value) return
      _syncAllChannelSubscriptions()
    },
  )

  return {
    channels,
    activeChannelRef,
    activeChannel,
    messages,
    unreadTotal,
    dmUnreadPeers,
    dmChannels,
    dmDialogOpen,
    dmChannelRef,
    dmActiveChannel,
    dmMessages,
    dmDraft,
    dmHistoryLimit,
    party,
    pendingInvites,
    outgoingInvites,
    waitingInvite,
    partyLimits,
    loading,
    lastError,
    dockOpen,
    draft,
    sessionEphemeral,
    sessionListening,
    refreshChannels,
    refreshPartyMe,
    loadHistory,
    loadDmHistory,
    selectChannel,
    selectDm,
    send,
    sendDm,
    clearDm,
    createParty,
    inviteToParty,
    convertToTeam,
    convertToParty,
    acceptPartyInvite,
    rejectPartyInvite,
    leaveParty,
    kickFromParty,
    applyPush,
    startPollingFallback,
    stopPollingFallback,
    startSessionListening,
    openDock,
    openDm,
    openDmDialog,
    closeDmDialog,
    closeDock,
    clearSession,
    bindPageHideClear,
  }
})
