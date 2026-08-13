/**
 * M7 L7 双修 Pinia store。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  cancelDual,
  confirmDual,
  fetchDualMe,
  fetchDualRanks,
  inviteDual,
  setDualGender,
  startDual,
  undressDual,
} from '../api/dualCultivation'
import type {
  DualBondKind,
  DualGender,
  DualInviteTarget,
  DualMePayload,
  DualRanksPayload,
  DualSession,
  DualTechnique,
} from '../types/dualCultivation'
import type { WsEnvelope } from '../types/ws'
import { notifyInviteJump } from '../utils/inviteNotify'
import { WsType } from '../ws/protocol'
import { useCharacterStore } from './character'

export const useDualCultivationStore = defineStore('dualCultivation', () => {
  const me = ref<DualMePayload | null>(null)
  const session = ref<DualSession | null>(null)
  const techniques = ref<DualTechnique[]>([])
  const inviteTargets = ref<{
    companions: DualInviteTarget[]
    vessels: DualInviteTarget[]
    vessel_invite_enabled?: boolean
    hint_zh?: string
  } | null>(null)
  const ranks = ref<DualRanksPayload | null>(null)
  const lastMessage = ref('')
  const lastSummary = ref<Record<string, unknown> | null>(null)
  const loading = ref(false)

  const primaryBoard = computed(
    () => ranks.value?.primary_board || 'duration_total',
  )

  const hasActiveSession = computed(() => {
    const s = session.value?.status
    return Boolean(s && ['inviting', 'accepted', 'undressed', 'running', 'confirmed'].includes(s))
  })

  async function refreshMe(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await fetchDualMe()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `加载双修失败（code=${envelope.code}）`
      }
      me.value = envelope.data
      session.value = envelope.data.session
      techniques.value = envelope.data.techniques || []
      inviteTargets.value = envelope.data.invite_targets || {
        companions: [],
        vessels: [],
      }
      return null
    } finally {
      loading.value = false
    }
  }

  function applyPush(envelope: WsEnvelope): void {
    if (
      envelope.type !== WsType.DUAL_INVITE &&
      envelope.type !== WsType.DUAL_UPDATE
    ) {
      return
    }
    const p = (envelope.payload || {}) as {
      event?: string
      message?: string
      bond_kind?: string
      summary?: Record<string, unknown>
    }
    const msg = String(p.message || '').trim()
    if (msg) {
      lastMessage.value = msg
    }
    if (p.summary && typeof p.summary === 'object') {
      lastSummary.value = p.summary
    }
    const event = String(p.event || '')
    const isVessel = String(p.bond_kind || '').toLowerCase() === 'vessel'
    const sessionId = Number(
      (p as { session_id?: number }).session_id ||
        (p.summary as { session_id?: number } | undefined)?.session_id ||
        0,
    )
    const isInviteType = envelope.type === WsType.DUAL_INVITE
    const title = isInviteType
      ? isVessel
        ? '炉鼎双修邀约'
        : '道侣双修邀约'
      : event === 'accepted'
        ? '双修已接受'
        : event === 'undressed'
          ? '对方已宽衣'
          : event === 'settled'
            ? '双修已完成'
            : event === 'cancelled' || event === 'timeout'
              ? '双修已结束'
              : ''
    const type =
      event === 'settled' || event === 'accepted' || event === 'undressed'
        ? 'success'
        : event === 'cancelled' || event === 'timeout'
          ? 'warning'
          : 'info'
    const shouldNotify =
      Boolean(msg) &&
      (isInviteType ||
        event === 'accepted' ||
        event === 'undressed' ||
        event === 'settled' ||
        event === 'cancelled' ||
        event === 'timeout')
    if (shouldNotify && title) {
      notifyInviteJump({
        title,
        message: msg,
        type,
        dedupeKey:
          sessionId > 0
            ? `dual:${isInviteType ? 'invite' : event}:${sessionId}`
            : `dual:${isInviteType ? 'invite' : event}:${msg.slice(0, 24)}`,
        to: { path: '/social', query: { mode: 'dual' } },
        afterNavigate: () => refreshMe(),
      })
    }
    void refreshMe()
    if (event === 'settled') {
      void loadRanks()
    }
  }

  async function chooseGender(gender: DualGender): Promise<string | null> {
    const envelope = await setDualGender(gender)
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '补选性别失败'
    }
    me.value = envelope.data
    session.value = envelope.data.session
    inviteTargets.value = envelope.data.invite_targets || inviteTargets.value
    lastMessage.value = '道途阴阳已定'
    await useCharacterStore().fetchMe()
    return null
  }

  async function invite(
    techniqueId: string,
    targetCharacterId: number,
    bondKind: DualBondKind,
  ): Promise<string | null> {
    const envelope = await inviteDual({
      technique_id: techniqueId,
      target_character_id: targetCharacterId,
      bond_kind: bondKind,
      inviter_role: 'number_one',
    })
    if (envelope.code !== 0) {
      return envelope.message || '邀约失败'
    }
    lastMessage.value = envelope.data?.message || '邀约已发送'
    lastSummary.value = null
    await refreshMe()
    return null
  }

  async function confirm(sessionId: number): Promise<string | null> {
    const envelope = await confirmDual(sessionId)
    if (envelope.code !== 0) return envelope.message || '确认失败'
    lastMessage.value = envelope.data?.message || '已确认'
    await refreshMe()
    return null
  }

  async function undress(sessionId: number): Promise<string | null> {
    const envelope = await undressDual(sessionId)
    if (envelope.code !== 0) return envelope.message || '宽衣失败'
    lastMessage.value = envelope.data?.message || '已宽衣'
    await refreshMe()
    return null
  }

  async function start(sessionId: number): Promise<string | null> {
    const envelope = await startDual(sessionId)
    if (envelope.code !== 0) return envelope.message || '开始失败'
    lastMessage.value = envelope.data?.message || '双修已结束'
    lastSummary.value = (envelope.data?.summary as Record<string, unknown>) || null
    if (envelope.data?.character) {
      useCharacterStore().applyCharacter(envelope.data.character as never)
    }
    await refreshMe()
    await loadRanks()
    return null
  }

  async function cancel(sessionId: number): Promise<string | null> {
    const envelope = await cancelDual(sessionId)
    if (envelope.code !== 0) return envelope.message || '取消失败'
    lastMessage.value = envelope.data?.message || '已取消'
    await refreshMe()
    return null
  }

  async function loadRanks(board?: string): Promise<string | null> {
    const envelope = await fetchDualRanks(
      board ? { board, limit: 100 } : { limit: 100 },
    )
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '加载时长榜失败'
    }
    ranks.value = envelope.data
    return null
  }

  return {
    me,
    session,
    techniques,
    inviteTargets,
    ranks,
    primaryBoard,
    hasActiveSession,
    lastMessage,
    lastSummary,
    loading,
    refreshMe,
    applyPush,
    chooseGender,
    invite,
    confirm,
    undress,
    start,
    cancel,
    loadRanks,
  }
})
