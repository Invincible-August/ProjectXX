/**
 * M7 L5 机缘（聊天室红包）Pinia store。
 *
 * 进行中由服务端拉取；已抢完在本会话内保留（默认 20 条），退出登录 / 关浏览器清空。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { claimHeritage, createHeritage, listHeritage } from '../api/heritage'
import type { HeritagePacket } from '../types/heritage'
import type { WsEnvelope } from '../types/ws'
import { WsType } from '../ws/protocol'
import { useCharacterStore } from './character'

const DEFAULT_FINISHED_KEEP = 20

/**
 * 规范化机缘包字段，避免缺省 status / 脏缓存导致「刚发出已领完」。
 *
 * @param raw - 原始包
 */
function normalizePacket(
  raw: Partial<HeritagePacket> & { id?: number },
): HeritagePacket | null {
  const id = Number(raw?.id || 0)
  if (!id) return null
  const shareCount = Math.max(0, Number(raw.share_count || 0))
  const sharesClaimed = Math.max(0, Number(raw.shares_claimed || 0))
  let status = String(raw.status || 'open').trim().toLowerCase()
  if (status !== 'exhausted' && status !== 'expired') {
    status = 'open'
  }
  // 尚未有人领取时，禁止保持 exhausted（防 id 复用脏缓存）
  if (status === 'exhausted' && sharesClaimed <= 0) {
    status = 'open'
  }
  if (status === 'open' && shareCount > 0 && sharesClaimed >= shareCount) {
    status = 'exhausted'
  }
  const alreadyClaimed = Boolean(raw.already_claimed)
  const canClaim =
    status === 'open' &&
    !alreadyClaimed &&
    (shareCount <= 0 || sharesClaimed < shareCount)
  return {
    id,
    channel_type: String(raw.channel_type || ''),
    channel_ref: String(raw.channel_ref || ''),
    room_id: String(raw.room_id || ''),
    sender_character_id: Number(raw.sender_character_id || 0),
    sender_name: String(raw.sender_name || ''),
    mode: (raw.mode as HeritagePacket['mode']) || 'fixed',
    mode_label_zh: String(raw.mode_label_zh || ''),
    share_count: shareCount,
    shares_claimed: sharesClaimed,
    spirit_stones_total: Number(raw.spirit_stones_total || 0),
    items: Array.isArray(raw.items) ? raw.items : [],
    status,
    note_zh: String(raw.note_zh || ''),
    expires_at: (raw.expires_at as string | null) ?? null,
    created_at: (raw.created_at as string | null) ?? null,
    already_claimed: alreadyClaimed,
    can_claim: typeof raw.can_claim === 'boolean' ? raw.can_claim && canClaim : canClaim,
  }
}

export const useHeritageStore = defineStore('heritage', () => {
  const packets = ref<HeritagePacket[]>([])
  /** 本会话已抢完机缘（按频道缓存，退出/关浏览器清空） */
  const finishedByChannel = ref<Record<string, HeritagePacket[]>>({})
  const loading = ref(false)
  const lastMessage = ref('')
  const lastError = ref('')
  const highlightId = ref<number | null>(null)
  const sessionFinishedKeep = ref(DEFAULT_FINISHED_KEEP)
  const activeChannelRef = ref<string | null>(null)

  /**
   * 退出登录 / 关闭浏览器：清空本端机缘（含已抢完会话缓存）。
   */
  function clearSession(): void {
    packets.value = []
    finishedByChannel.value = {}
    lastMessage.value = ''
    lastError.value = ''
    highlightId.value = null
    activeChannelRef.value = null
  }

  /**
   * 是否为「已抢完」可本会话保留的包。
   *
   * @param p - 机缘包
   */
  function isFinishedPacket(p: HeritagePacket): boolean {
    return String(p.status || '') === 'exhausted'
  }

  /**
   * 写入本会话已抢完缓存并裁剪条数。
   *
   * @param p - 已抢完机缘
   */
  function rememberFinished(p: HeritagePacket): void {
    if (!isFinishedPacket(p) || !p.channel_ref) return
    const channelRef = p.channel_ref
    const prev = finishedByChannel.value[channelRef] ?? []
    const next = [p, ...prev.filter((x) => x.id !== p.id)]
      .sort((a, b) => b.id - a.id)
      .slice(0, Math.max(0, sessionFinishedKeep.value))
    finishedByChannel.value = {
      ...finishedByChannel.value,
      [channelRef]: next,
    }
  }

  /**
   * 从已抢完缓存移除某 id（新包 open 时清掉同 id 脏缓存）。
   *
   * @param channelRef - 频道
   * @param packetId - 包 id
   */
  function forgetFinished(channelRef: string, packetId: number): void {
    const prev = finishedByChannel.value[channelRef] ?? []
    if (!prev.some((x) => x.id === packetId)) return
    finishedByChannel.value = {
      ...finishedByChannel.value,
      [channelRef]: prev.filter((x) => x.id !== packetId),
    }
  }

  /**
   * 合并服务端进行中列表 + 本会话已抢完缓存，供 UI 展示。
   *
   * @param channelRef - 当前频道
   * @param openItems - 服务端 open 列表
   */
  function rebuildVisible(channelRef: string, openItems: HeritagePacket[]): void {
    const normalizedOpen = openItems
      .map((item) => normalizePacket(item))
      .filter((item): item is HeritagePacket => item != null && item.status === 'open')
    // 进行中的 id 不得再保留「已领完」脏缓存（SQLite id 复用）
    for (const item of normalizedOpen) {
      forgetFinished(channelRef, item.id)
    }
    const finished = [...(finishedByChannel.value[channelRef] ?? [])]
      .map((item) => normalizePacket(item))
      .filter((item): item is HeritagePacket => item != null && isFinishedPacket(item))
      .slice(0, Math.max(0, sessionFinishedKeep.value))
    const openIds = new Set(normalizedOpen.map((p) => p.id))
    const finishedOnly = finished.filter((p) => !openIds.has(p.id))
    packets.value = [...normalizedOpen, ...finishedOnly].sort((a, b) => a.id - b.id)
  }

  /**
   * 就地更新可见列表中的一条，并按需记入已抢完缓存。
   *
   * @param raw - 机缘包
   */
  function upsertPacket(raw: Partial<HeritagePacket>): void {
    const p = normalizePacket(raw)
    if (!p) return
    const channelRef = p.channel_ref || activeChannelRef.value
    if (!channelRef) {
      packets.value = [p, ...packets.value.filter((x) => x.id !== p.id)]
      return
    }
    p.channel_ref = channelRef

    if (p.status === 'open') {
      forgetFinished(channelRef, p.id)
    } else if (isFinishedPacket(p)) {
      rememberFinished(p)
    } else if (p.status === 'expired') {
      forgetFinished(channelRef, p.id)
    }

    const open = packets.value
      .filter(
        (x) =>
          x.channel_ref === channelRef && x.status === 'open' && x.id !== p.id,
      )
      .map((x) => normalizePacket(x))
      .filter((x): x is HeritagePacket => x != null)

    if (p.status === 'open') {
      open.unshift(p)
    }
    rebuildVisible(channelRef, open)
  }

  async function refresh(channelRef: string | null): Promise<string | null> {
    activeChannelRef.value = channelRef
    if (!channelRef) {
      packets.value = []
      return null
    }
    loading.value = true
    lastError.value = ''
    try {
      const envelope = await listHeritage(channelRef)
      if (envelope.code !== 0 || !envelope.data) {
        rebuildVisible(channelRef, [])
        const msg = envelope.message || `加载机缘失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      if (typeof envelope.data.session_finished_keep === 'number') {
        sessionFinishedKeep.value = Math.max(0, Number(envelope.data.session_finished_keep))
      }
      rebuildVisible(channelRef, envelope.data.items ?? [])
      return null
    } finally {
      loading.value = false
    }
  }

  async function create(body: {
    channel_ref: string
    mode: 'random' | 'fixed'
    share_count: number
    spirit_stones?: number
    items?: Array<{ item_id: string; quantity: number }>
    note_zh?: string
  }): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await createHeritage(body)
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `发机缘失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      lastMessage.value = envelope.data.message || '机缘已发出'
      if (envelope.data.character) {
        useCharacterStore().applyCharacter(envelope.data.character as never)
      }
      if (envelope.data.packet) {
        // 强制按「新发出」归一：避免脏字段把新包标成已领完
        const fresh = normalizePacket({
          ...envelope.data.packet,
          status: 'open',
          shares_claimed: Number(envelope.data.packet.shares_claimed || 0),
          already_claimed: false,
          can_claim: true,
        })
        if (fresh) {
          highlightId.value = fresh.id
          upsertPacket(fresh)
        }
      }
      return null
    } finally {
      loading.value = false
    }
  }

  async function claim(packetId: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await claimHeritage(packetId)
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `开缘失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      lastMessage.value = envelope.data.message || '开缘成功'
      if (envelope.data.character) {
        useCharacterStore().applyCharacter(envelope.data.character as never)
      }
      if (envelope.data.packet) {
        const p = normalizePacket({
          ...envelope.data.packet,
          already_claimed: true,
          can_claim: false,
        })
        if (p) {
          highlightId.value = p.id
          upsertPacket(p)
        }
      }
      return null
    } finally {
      loading.value = false
    }
  }

  function applyPush(envelope: WsEnvelope): void {
    if (envelope.type === WsType.HERITAGE_CREATED) {
      const p = normalizePacket(envelope.payload as Partial<HeritagePacket>)
      if (!p) return
      // 推送新包一律视为可领的进行中（防脏 status）
      const fresh = normalizePacket({
        ...p,
        status: 'open',
        already_claimed: Boolean(p.already_claimed),
        can_claim: !p.already_claimed,
      })
      if (!fresh) return
      highlightId.value = fresh.id
      upsertPacket(fresh)
      return
    }
    if (envelope.type === WsType.HERITAGE_CLAIMED) {
      const payload = envelope.payload as {
        packet_id?: number
        status?: string
        shares_claimed?: number
        share_count?: number
        channel_ref?: string
        packet_created_at?: string | null
      }
      const packetId = Number(payload.packet_id || 0)
      if (!packetId) return
      const existing = packets.value.find((x) => x.id === packetId)
      // 迟到的 claimed：若本地包创建时间更新，说明 id 已复用为新包，忽略旧推送
      const pushCreated = String(payload.packet_created_at || '')
      const localCreated = String(existing?.created_at || '')
      if (
        pushCreated &&
        localCreated &&
        pushCreated !== localCreated &&
        existing?.status === 'open'
      ) {
        return
      }
      const status = String(payload.status || existing?.status || 'open')
      const claimed = Number(payload.shares_claimed ?? existing?.shares_claimed ?? 0)
      const channelRef = String(
        payload.channel_ref || existing?.channel_ref || activeChannelRef.value || '',
      )
      if (!existing && !channelRef) return
      const updated = normalizePacket({
        id: packetId,
        channel_type: existing?.channel_type || '',
        channel_ref: channelRef || existing?.channel_ref || '',
        room_id: existing?.room_id || '',
        sender_character_id: existing?.sender_character_id || 0,
        sender_name: existing?.sender_name || '',
        mode: existing?.mode || 'fixed',
        mode_label_zh: existing?.mode_label_zh || '',
        share_count: Number(payload.share_count ?? existing?.share_count ?? 0),
        shares_claimed: claimed,
        spirit_stones_total: existing?.spirit_stones_total ?? 0,
        items: existing?.items ?? [],
        status,
        note_zh: existing?.note_zh || '',
        expires_at: existing?.expires_at ?? null,
        created_at: existing?.created_at ?? (pushCreated || null),
        already_claimed: existing?.already_claimed ?? false,
        can_claim: false,
      })
      if (updated) {
        if (updated.status === 'open') {
          updated.can_claim = !updated.already_claimed
        }
        upsertPacket(updated)
      }
      return
    }
    if (envelope.type === WsType.HERITAGE_EXPIRED) {
      const packetId = Number((envelope.payload as { packet_id?: number }).packet_id || 0)
      if (!packetId) return
      const existing = packets.value.find((x) => x.id === packetId)
      const channelRef = existing?.channel_ref || activeChannelRef.value
      if (channelRef) {
        forgetFinished(channelRef, packetId)
        const open = packets.value.filter(
          (x) => x.channel_ref === channelRef && x.status === 'open' && x.id !== packetId,
        )
        rebuildVisible(channelRef, open)
      } else {
        packets.value = packets.value.filter((x) => x.id !== packetId)
      }
    }
  }

  return {
    packets,
    loading,
    lastMessage,
    lastError,
    highlightId,
    sessionFinishedKeep,
    refresh,
    create,
    claim,
    applyPush,
    clearSession,
  }
})
