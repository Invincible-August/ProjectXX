/**
 * M7 L2 交易 Pinia store：挂单 / 拍卖 / 面交。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  bidAuction,
  buyFromBazaar,
  buyListing,
  cancelListing,
  createAuction,
  createListing,
  faceAccept,
  faceCancel,
  faceConfirm,
  faceGet,
  faceInvite,
  faceInviteOptions,
  faceListPending,
  faceLock,
  faceOffer,
  faceReject,
  fetchBazaar,
  listAuctions,
  listListings,
  sellToBazaar,
} from '../api/trade'
import type {
  AuctionLot,
  BazaarCatalogPayload,
  FaceInviteOptions,
  FacePendingInvite,
  FaceSession,
  Listing,
  TradeItemLine,
} from '../types/trade'
import type { WsEnvelope } from '../types/ws'
import { notifyInviteJump } from '../utils/inviteNotify'
import { WsType } from '../ws/protocol'
import { useCharacterStore } from './character'

export const useTradeStore = defineStore('trade', () => {
  /** 交易行开放挂单 */
  const listings = ref<Listing[]>([])
  /** 开放拍品 */
  const auctions = ref<AuctionLot[]>([])
  /** 当前交易会话（单会话工作台） */
  const faceSession = ref<FaceSession | null>(null)
  /** 快捷选人选项 */
  const inviteOptions = ref<FaceInviteOptions | null>(null)
  /** 收到的待接受交易邀请 */
  const pendingInvites = ref<FacePendingInvite[]>([])
  /** NPC 坊市货架 */
  const bazaar = ref<BazaarCatalogPayload | null>(null)
  const loading = ref(false)
  const lastMessage = ref('')
  const lastError = ref('')

  /**
   * 若结果含 character，回写角色面板（灵石等）。
   *
   * @param character - 可选角色
   */
  function applyCharacter(
    character?: import('../types/character').CharacterPublic,
  ): void {
    if (character) {
      useCharacterStore().applyCharacter(character)
    }
  }

  /** 刷新交易行列表 */
  async function refreshListings(): Promise<string | null> {
    loading.value = true
    lastError.value = ''
    try {
      const envelope = await listListings()
      if (envelope.code !== 0 || !envelope.data) {
        listings.value = []
        const msg =
          envelope.message || `加载交易行失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      listings.value = envelope.data.items ?? []
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 一口价上架（单物品行简化表单）。
   *
   * @param itemId - 物品 id
   * @param quantity - 数量
   * @param priceSpiritStones - 灵石标价
   */
  async function createFixedPriceListing(
    itemId: string,
    quantity: number,
    priceSpiritStones: number,
  ): Promise<string | null> {
    const id = itemId.trim()
    if (!id) {
      const msg = '请填写物品 id'
      lastError.value = msg
      return msg
    }
    if (quantity < 1 || priceSpiritStones < 1) {
      const msg = '数量与标价须为正整数'
      lastError.value = msg
      return msg
    }
    loading.value = true
    try {
      const envelope = await createListing({
        mode: 'fixed_price',
        offer_items: [{ item_id: id, quantity }],
        price_spirit_stones: priceSpiritStones,
        ask_items: [],
      })
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `上架失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      applyCharacter(envelope.data.character)
      lastMessage.value = envelope.data.message || '已上架'
      await refreshListings()
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 购买挂单。
   *
   * @param listingId - 挂单 id
   */
  async function buy(listingId: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await buyListing(listingId)
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `购买失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      applyCharacter(envelope.data.character)
      lastMessage.value = envelope.data.message || '成交成功'
      await refreshListings()
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 撤自己的挂单。
   *
   * @param listingId - 挂单 id
   */
  async function cancel(listingId: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await cancelListing(listingId)
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `撤单失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      applyCharacter(envelope.data.character)
      lastMessage.value = envelope.data.message || '已撤单'
      await refreshListings()
      return null
    } finally {
      loading.value = false
    }
  }

  /** 刷新拍卖列表 */
  async function refreshAuctions(): Promise<string | null> {
    loading.value = true
    lastError.value = ''
    try {
      const envelope = await listAuctions()
      if (envelope.code !== 0 || !envelope.data) {
        auctions.value = []
        const msg =
          envelope.message || `加载拍卖失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      auctions.value = envelope.data.items ?? []
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 上架拍品（单物品行）。
   *
   * @param itemId - 物品 id
   * @param quantity - 数量
   * @param startPrice - 起拍灵石
   * @param durationSec - 可选时长秒
   */
  async function createLot(
    itemId: string,
    quantity: number,
    startPrice: number,
    durationSec?: number | null,
  ): Promise<string | null> {
    const id = itemId.trim()
    if (!id) {
      const msg = '请填写物品 id'
      lastError.value = msg
      return msg
    }
    if (quantity < 1 || startPrice < 1) {
      const msg = '数量与起拍价须为正整数'
      lastError.value = msg
      return msg
    }
    loading.value = true
    try {
      const envelope = await createAuction({
        offer_items: [{ item_id: id, quantity }],
        start_price: startPrice,
        duration_sec: durationSec ?? null,
      })
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `上架拍卖失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      applyCharacter(envelope.data.character)
      lastMessage.value = envelope.data.message || '拍品已上架'
      await refreshAuctions()
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 对拍品出价。
   *
   * @param lotId - 拍品 id
   * @param amount - 出价灵石
   */
  async function bid(lotId: number, amount: number): Promise<string | null> {
    if (amount < 1) {
      const msg = '出价须为正整数'
      lastError.value = msg
      return msg
    }
    loading.value = true
    try {
      const envelope = await bidAuction(lotId, { amount })
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `出价失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      applyCharacter(envelope.data.character)
      lastMessage.value = envelope.data.message || '出价成功'
      await refreshAuctions()
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 按道号或角色 id 发起面交。
   *
   * @param opts - peer_name 或 peer_character_id
   */
  async function inviteFace(opts: {
    peer_name?: string | null
    peer_character_id?: number | null
  }): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await faceInvite(opts)
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `发起面交失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      faceSession.value = envelope.data.session ?? null
      lastMessage.value = envelope.data.message || '已发起面交'
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 拉取面交会话状态。
   *
   * @param sessionId - 会话 id
   */
  async function loadFace(sessionId: number): Promise<string | null> {
    loading.value = true
    lastError.value = ''
    try {
      const envelope = await faceGet(sessionId)
      if (envelope.code !== 0 || !envelope.data) {
        faceSession.value = null
        const msg =
          envelope.message || `加载面交失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      faceSession.value = envelope.data.session ?? null
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 更新己方面交草稿报价（不托管；会清锁定/确认）。
   *
   * @param items - 物品行
   * @param spiritStones - 灵石
   */
  async function setFaceOffer(
    items: TradeItemLine[],
    spiritStones: number,
    vesselOffer?: { hours: number } | null,
  ): Promise<string | null> {
    const session = faceSession.value
    if (!session) {
      const msg = '尚无面交会话'
      lastError.value = msg
      return msg
    }
    loading.value = true
    try {
      const envelope = await faceOffer(session.id, {
        items,
        spirit_stones: spiritStones,
        vessel_offer: vesselOffer ?? null,
        version: session.version,
      })
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `更新报价失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      applyCharacter(envelope.data.character)
      faceSession.value = envelope.data.session ?? faceSession.value
      lastMessage.value = envelope.data.message || '报价已更新'
      return null
    } finally {
      loading.value = false
    }
  }

  /** 受邀方接受面交 */
  async function acceptFace(): Promise<string | null> {
    const session = faceSession.value
    if (!session) {
      const msg = '尚无面交会话'
      lastError.value = msg
      return msg
    }
    loading.value = true
    try {
      const envelope = await faceAccept(session.id)
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `接受失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      faceSession.value = envelope.data.session ?? faceSession.value
      lastMessage.value = envelope.data.message || '已接受'
      return null
    } finally {
      loading.value = false
    }
  }

  /** 受邀方拒绝面交 */
  async function rejectFace(): Promise<string | null> {
    const session = faceSession.value
    if (!session) {
      const msg = '尚无面交会话'
      lastError.value = msg
      return msg
    }
    loading.value = true
    try {
      const envelope = await faceReject(session.id)
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `拒绝失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      faceSession.value = envelope.data.session ?? null
      lastMessage.value = envelope.data.message || '已拒绝'
      return null
    } finally {
      loading.value = false
    }
  }

  /** 锁定己方报价并托管 */
  async function lockFace(): Promise<string | null> {
    const session = faceSession.value
    if (!session) {
      const msg = '尚无面交会话'
      lastError.value = msg
      return msg
    }
    loading.value = true
    try {
      const envelope = await faceLock(session.id, {
        version: session.version,
      })
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `锁定失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      applyCharacter(envelope.data.character)
      faceSession.value = envelope.data.session ?? faceSession.value
      lastMessage.value = envelope.data.message || '已锁定'
      return null
    } finally {
      loading.value = false
    }
  }

  /** 确认面交（双方锁定后；双方确认后成交） */
  async function confirmFace(): Promise<string | null> {
    const session = faceSession.value
    if (!session) {
      const msg = '尚无面交会话'
      lastError.value = msg
      return msg
    }
    loading.value = true
    try {
      const envelope = await faceConfirm(session.id, {
        version: session.version,
      })
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `确认失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      applyCharacter(envelope.data.character)
      faceSession.value = envelope.data.session ?? faceSession.value
      lastMessage.value = envelope.data.message || '已确认'
      return null
    } finally {
      loading.value = false
    }
  }

  /** 取消面交并退回已托管侧 */
  async function cancelFace(): Promise<string | null> {
    const session = faceSession.value
    if (!session) {
      const msg = '尚无面交会话'
      lastError.value = msg
      return msg
    }
    loading.value = true
    try {
      const envelope = await faceCancel(session.id)
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `取消失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      applyCharacter(envelope.data.character)
      faceSession.value = envelope.data.session ?? null
      lastMessage.value = envelope.data.message || '面交已取消'
      return null
    } finally {
      loading.value = false
    }
  }

  /** 清空本地面交工作台 */
  function clearFaceSession(): void {
    faceSession.value = null
  }

  /**
   * Hot-update face session peer_online from presence push.
   *
   * @param characterId - Peer character id
   * @param online - New flag
   */
  function applyPresence(characterId: number, online: boolean): void {
    const s = faceSession.value
    if (!s) return
    const counterparty =
      s.you_are === 'initiator' ? Number(s.peer_id) : Number(s.initiator_id)
    if (counterparty !== Number(characterId)) return
    faceSession.value = { ...s, peer_online: online }
  }

  /**
   * 带短重试刷新待接受列表（应对提交与推送的微小时差）。
   *
   * @param expectSessionId - 期望出现的会话 id；有则未出现时重试
   */
  async function refreshPendingWithRetry(
    expectSessionId?: number | null,
  ): Promise<string | null> {
    const expect = Number(expectSessionId || 0)
    let lastErr: string | null = null
    for (let i = 0; i < 4; i += 1) {
      lastErr = await refreshPending()
      if (expect <= 0) return lastErr
      if (pendingInvites.value.some((x) => Number(x.session_id) === expect)) {
        return lastErr
      }
      await new Promise((r) => setTimeout(r, 120 * (i + 1)))
    }
    return lastErr
  }

  /**
   * 邀请推送乐观写入待接受列表，避免等接口才出按钮。
   */
  function upsertPendingFromInvite(p: {
    session_id?: number
    from_character_id?: number
    from_name?: string
    expires_at?: string | null
    status?: string
    invite_kind?: string
    invite_kind_label_zh?: string
  }): void {
    const sid = Number(p.session_id || 0)
    if (sid <= 0) return
    const rest = pendingInvites.value.filter((x) => Number(x.session_id) !== sid)
    pendingInvites.value = [
      {
        session_id: sid,
        from_character_id: Number(p.from_character_id || 0),
        from_name: String(p.from_name || '对方'),
        status: String(p.status || 'pending_invite'),
        expires_at: p.expires_at ?? null,
        invite_kind: p.invite_kind,
        invite_kind_label_zh: p.invite_kind_label_zh || '交易',
      },
      ...rest,
    ]
  }

  /**
   * Handle face.invite / face.update WS pushes (notify + refresh pending).
   *
   * @param envelope - WS envelope
   */
  function applyPush(envelope: WsEnvelope): void {
    if (
      envelope.type !== WsType.FACE_INVITE &&
      envelope.type !== WsType.FACE_UPDATE
    ) {
      return
    }
    const p = (envelope.payload || {}) as {
      event?: string
      message?: string
      session_id?: number
      from_character_id?: number
      from_name?: string
      expires_at?: string | null
      status?: string
      invite_kind?: string
      invite_kind_label_zh?: string
      session?: FaceSession
    }
    const msg = String(p.message || '').trim()
    if (msg) {
      lastMessage.value = msg
    }
    const event = String(p.event || '')
    const isInvitePush =
      envelope.type === WsType.FACE_INVITE || event === 'invite'
    const sid = Number(p.session_id || p.session?.id || 0)

    if (isInvitePush) {
      upsertPendingFromInvite(p)
    }

    // 邀请不自动打开会话；点通知进交易页后手动接受
    if (p.session && typeof p.session === 'object' && !isInvitePush) {
      const cur = faceSession.value
      if (!cur || Number(cur.id) === Number(p.session.id)) {
        faceSession.value = p.session
      }
    }

    // 终态时从待接受列表移除
    if (
      sid > 0 &&
      (event === 'accepted' ||
        event === 'rejected' ||
        event === 'cancelled' ||
        event === 'committed')
    ) {
      pendingInvites.value = pendingInvites.value.filter(
        (x) => Number(x.session_id) !== sid,
      )
    }

    const title =
      envelope.type === WsType.FACE_INVITE
        ? '交易邀请'
        : event === 'accepted'
          ? '交易已接受'
          : event === 'rejected' || event === 'cancelled'
            ? '交易已结束'
            : event === 'committed'
              ? '交易成交'
              : event === 'locked'
                ? '对方已锁定'
                : ''
    const type =
      event === 'committed' || event === 'accepted'
        ? 'success'
        : event === 'rejected' || event === 'cancelled'
          ? 'warning'
          : 'info'
    // 仅邀请与关键终态/锁定弹窗；草稿更新等不刷屏
    const shouldNotify =
      Boolean(msg) &&
      (envelope.type === WsType.FACE_INVITE ||
        event === 'accepted' ||
        event === 'rejected' ||
        event === 'cancelled' ||
        event === 'committed' ||
        event === 'locked')
    if (shouldNotify && title) {
      notifyInviteJump({
        title,
        message: msg,
        type,
        dedupeKey:
          sid > 0
            ? `face:${envelope.type === WsType.FACE_INVITE ? 'invite' : event}:${sid}`
            : undefined,
        to: {
          path: '/social',
          query: {
            mode: 'trade',
            ...(sid > 0 ? { session: String(sid) } : {}),
          },
        },
        afterNavigate: async () => {
          if (sid > 0) {
            await refreshPendingWithRetry(sid)
            await loadFace(sid)
          } else {
            await refreshPending()
          }
        },
      })
    }
    void refreshPendingWithRetry(isInvitePush ? sid : null)
  }

  /** 加载快捷选人 */
  async function loadInviteOptions(): Promise<string | null> {
    try {
      const envelope = await faceInviteOptions()
      if (envelope.code !== 0 || !envelope.data) {
        inviteOptions.value = null
        return envelope.message || '加载交易选人失败'
      }
      inviteOptions.value = envelope.data
      return null
    } catch (e: unknown) {
      return e instanceof Error ? e.message : '加载交易选人失败'
    }
  }

  /** 刷新收到的交易邀请 */
  async function refreshPending(): Promise<string | null> {
    try {
      const envelope = await faceListPending()
      if (envelope.code !== 0 || !envelope.data) {
        pendingInvites.value = []
        return envelope.message || '加载交易邀请失败'
      }
      pendingInvites.value = envelope.data.items ?? []
      return null
    } catch (e: unknown) {
      pendingInvites.value = []
      return e instanceof Error ? e.message : '加载交易邀请失败'
    }
  }

  /** 刷新 NPC 坊市货架 */
  async function refreshBazaar(): Promise<string | null> {
    loading.value = true
    lastError.value = ''
    try {
      const envelope = await fetchBazaar()
      if (envelope.code !== 0 || !envelope.data) {
        bazaar.value = null
        const msg = envelope.message || `加载坊市失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      bazaar.value = envelope.data
      const ch = useCharacterStore().character
      if (ch && typeof envelope.data.spirit_stones === 'number') {
        useCharacterStore().applyCharacter({
          ...ch,
          spirit_stones: envelope.data.spirit_stones,
        })
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 向坊市购买。
   *
   * @param itemId - 物品 id
   * @param quantity - 数量
   */
  async function bazaarBuy(itemId: string, quantity: number): Promise<string | null> {
    if (quantity < 1) {
      const msg = '数量须为正整数'
      lastError.value = msg
      return msg
    }
    loading.value = true
    try {
      const envelope = await buyFromBazaar(itemId, quantity)
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `购买失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      if (envelope.data.catalog) {
        bazaar.value = envelope.data.catalog
      }
      const ch = useCharacterStore().character
      if (ch && typeof envelope.data.spirit_stones === 'number') {
        useCharacterStore().applyCharacter({
          ...ch,
          spirit_stones: envelope.data.spirit_stones,
        })
      }
      lastMessage.value = envelope.data.message || '购买成功'
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 向坊市出售换灵石。
   *
   * @param itemId - 物品 id
   * @param quantity - 数量
   */
  async function bazaarSell(itemId: string, quantity: number): Promise<string | null> {
    if (quantity < 1) {
      const msg = '数量须为正整数'
      lastError.value = msg
      return msg
    }
    loading.value = true
    try {
      const envelope = await sellToBazaar(itemId, quantity)
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `出售失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      if (envelope.data.catalog) {
        bazaar.value = envelope.data.catalog
      }
      const ch = useCharacterStore().character
      if (ch && typeof envelope.data.spirit_stones === 'number') {
        useCharacterStore().applyCharacter({
          ...ch,
          spirit_stones: envelope.data.spirit_stones,
        })
      }
      lastMessage.value = envelope.data.message || '出售成功'
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    listings,
    auctions,
    faceSession,
    inviteOptions,
    pendingInvites,
    bazaar,
    loading,
    lastMessage,
    lastError,
    refreshListings,
    createFixedPriceListing,
    buy,
    cancel,
    refreshAuctions,
    createLot,
    bid,
    inviteFace,
    loadFace,
    setFaceOffer,
    acceptFace,
    rejectFace,
    lockFace,
    confirmFace,
    cancelFace,
    clearFaceSession,
    applyPresence,
    applyPush,
    loadInviteOptions,
    refreshPending,
    refreshPendingWithRetry,
    refreshBazaar,
    bazaarBuy,
    bazaarSell,
  }
})
