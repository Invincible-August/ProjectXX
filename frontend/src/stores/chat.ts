/**
 * M7 L4 聊天 Pinia store：频道 / 会话消息 / 发送 / WS 推送 / 轮询降级。
 *
 * 默认 ``session_ephemeral``：不拉服务端历史；退出登录 / 关闭浏览器清空本会话消息。
 */
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import {
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
import { useCharacterStore } from './character'
import { useHeritageStore } from './heritage'
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
  /** Local waiting hint after sending an invite */
  const waitingInvite = ref<PartyInviteItem | null>(null)
  const loading = ref(false)
  const lastError = ref('')
  const dockOpen = ref(false)
  const draft = ref('')
  /** 由 GET /chat/channels 下发；默认 true */
  const sessionEphemeral = ref(true)

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
    party.value = null
    pendingInvites.value = []
    waitingInvite.value = null
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
      const envelope = await fetchChatHistory({ channel_ref: channelRef, limit: 50 })
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

  async function selectChannel(channelRef: string | null): Promise<void> {
    _persistActiveSessionMessages()
    activeChannelRef.value = channelRef
    if (!channelRef) {
      messages.value = []
      return
    }
    if (sessionEphemeral.value) {
      await enterChannelLive(channelRef)
    } else {
      await loadHistory(channelRef)
    }
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
   * Refresh party + pending invites from GET /party/me.
   */
  async function refreshPartyMe(): Promise<string | null> {
    const envelope = await fetchPartyMe()
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || `加载队伍失败（code=${envelope.code}）`
    }
    party.value = envelope.data.party ?? null
    pendingInvites.value = envelope.data.pending_invites ?? []
    // Clear local waiting if invite resolved / accepted into party
    if (waitingInvite.value) {
      const stillPending = pendingInvites.value.some(
        (i) => i.id === waitingInvite.value?.id,
      )
      const members = party.value?.members ?? []
      const peerJoined = members.some(
        (m) => m.character_id === waitingInvite.value?.invitee_id,
      )
      if (peerJoined || (!stillPending && party.value)) {
        // Keep waiting until peer joins or invite leaves pending on invitee side;
        // inviter does not see own invite in pending_invites — clear when peer in party
        if (peerJoined) waitingInvite.value = null
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
    if (envelope.data?.pending_invites) {
      pendingInvites.value = envelope.data.pending_invites
    }
    await refreshChannels()
    return null
  }

  /**
   * Invite a peer by dao name (requires friends + online gate server-side).
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
    if (envelope.data?.pending_invites) {
      pendingInvites.value = envelope.data.pending_invites
    }
    await refreshChannels()
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
    pendingInvites.value = envelope.data?.pending_invites ?? []
    await refreshChannels()
    return null
  }

  function applyPush(envelope: WsEnvelope): void {
    if (
      envelope.type === WsType.HERITAGE_CREATED ||
      envelope.type === WsType.HERITAGE_CLAIMED ||
      envelope.type === WsType.HERITAGE_EXPIRED
    ) {
      useHeritageStore().applyPush(envelope)
      return
    }
    if (
      envelope.type === WsType.PARTY_INVITE ||
      envelope.type === WsType.PARTY_UPDATE
    ) {
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
   * 不依赖聊天坞是否打开、当前是否在某一页签。
   */
  async function startSessionListening(): Promise<void> {
    bindPageHideClear()
    ensureWsHandler()
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
    if (activeChannelRef.value) {
      const stillOk = channels.value.some(
        (c) =>
          c.channel_ref === activeChannelRef.value &&
          c.can_access &&
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
   * 打开聊天坞并切入与指定道友的私聊频。
   *
   * @param peerCharacterId - 对方角色 id
   */
  async function openDm(peerCharacterId: number): Promise<string | null> {
    const peerId = Number(peerCharacterId)
    if (!peerId) return '对方无效'
    await startSessionListening()
    dockOpen.value = true
    startPollingFallback()
    const dm = channels.value.find((c) => {
      if (c.channel_type !== 'dm') return false
      if (Number(c.peer_character_id) === peerId) return true
      const parts = String(c.channel_ref || '').split(':')
      return parts[0] === 'dm' && parts.slice(1).map(Number).includes(peerId)
    })
    if (!dm?.channel_ref) {
      return '尚未生成私聊频道，请确认已结为道友后重试'
    }
    await selectChannel(dm.channel_ref)
    return null
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
      if (st !== 'open') return
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
    party,
    pendingInvites,
    waitingInvite,
    loading,
    lastError,
    dockOpen,
    draft,
    sessionEphemeral,
    sessionListening,
    refreshChannels,
    refreshPartyMe,
    loadHistory,
    selectChannel,
    send,
    createParty,
    inviteToParty,
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
    closeDock,
    clearSession,
    bindPageHideClear,
  }
})
