/**
 * 道侣 / 炉鼎 Pinia store（含 WS 申请提示）。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  acceptBond,
  applyCompanion,
  listBonds,
  rejectBond,
  removeBond,
} from '../api/bonds'
import type { BondItem } from '../types/bonds'
import type { WsEnvelope } from '../types/ws'
import { notifyInviteJump } from '../utils/inviteNotify'
import { WsType } from '../ws/protocol'

export const useBondsStore = defineStore('bonds', () => {
  const companions = ref<BondItem[]>([])
  const vessels = ref<BondItem[]>([])
  const myMaster = ref<BondItem | null>(null)
  const companionIncoming = ref<BondItem[]>([])
  const companionOutgoing = ref<BondItem[]>([])
  const companionCount = ref(0)
  const vesselCount = ref(0)
  const maxCompanions = ref(0)
  const maxVessels = ref(0)
  const vesselInviteEnabled = ref(false)
  const vesselHintZh = ref('炉鼎玩法尚未开放，暂不可直接邀请添加')
  const lastMessage = ref('')
  const loading = ref(false)

  async function refresh(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await listBonds()
      if (envelope.code !== 0 || !envelope.data) {
        companions.value = []
        vessels.value = []
        myMaster.value = null
        companionIncoming.value = []
        companionOutgoing.value = []
        return envelope.message || `加载道侣/炉鼎失败（code=${envelope.code}）`
      }
      const d = envelope.data
      companions.value = d.companions ?? []
      vessels.value = d.vessels ?? []
      myMaster.value = d.my_master ?? null
      companionIncoming.value = d.companion_incoming ?? []
      companionOutgoing.value = d.companion_outgoing ?? []
      companionCount.value = Number(d.companion_count ?? 0)
      vesselCount.value = Number(d.vessel_count ?? 0)
      maxCompanions.value = Number(d.max_companions ?? 0)
      maxVessels.value = Number(d.max_vessels ?? 0)
      vesselInviteEnabled.value = Boolean(d.vessel_invite_enabled)
      vesselHintZh.value = d.vessel_hint_zh || vesselHintZh.value
      return null
    } finally {
      loading.value = false
    }
  }

  /** Handle bond.request / bond.update WS pushes. */
  function applyPush(envelope: WsEnvelope): void {
    if (
      envelope.type !== WsType.BOND_REQUEST &&
      envelope.type !== WsType.BOND_UPDATE
    ) {
      return
    }
    const p = (envelope.payload || {}) as {
      event?: string
      message?: string
      from_name?: string
    }
    const msg =
      String(p.message || '').trim() ||
      (envelope.type === WsType.BOND_REQUEST
        ? '你有新的道侣申请'
        : '道侣申请状态已更新')
    const event = String(p.event || '')
    const title =
      event === 'accepted'
        ? '道侣同意'
        : event === 'rejected'
          ? '道侣拒绝'
          : '道侣申请'
    const type =
      event === 'accepted' ? 'success' : event === 'rejected' ? 'warning' : 'info'
    notifyInviteJump({
      title,
      message: msg,
      type,
      dedupeKey: `bond:${event || envelope.type}:${String(p.from_name || msg).slice(0, 32)}`,
      to: { path: '/social', query: { mode: 'friends' } },
      afterNavigate: () => refresh(),
    })
    void refresh()
  }

  async function applyByName(targetName: string): Promise<string | null> {
    const name = targetName.trim()
    if (!name) return '请输入对方道号'
    loading.value = true
    try {
      const envelope = await applyCompanion({ target_name: name })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `申请道侣失败（code=${envelope.code}）`
      }
      lastMessage.value = envelope.data.message || '已发送道侣申请'
      await refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  async function applyByCharacterId(characterId: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await applyCompanion({ target_character_id: characterId })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `申请道侣失败（code=${envelope.code}）`
      }
      lastMessage.value = envelope.data.message || '已发送道侣申请'
      await refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  async function accept(bondId: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await acceptBond(bondId)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '确认失败'
      }
      lastMessage.value = envelope.data.message || '已结为道侣'
      await refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  async function reject(bondId: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await rejectBond(bondId)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '拒绝失败'
      }
      lastMessage.value = envelope.data.message || '已拒绝'
      await refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  async function remove(bondId: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await removeBond(bondId)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '解除失败'
      }
      lastMessage.value = envelope.data.message || '已解除'
      await refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  function applyPresence(characterId: number, online: boolean): void {
    const cid = Number(characterId)
    const patch = (list: BondItem[]) =>
      list.map((x) =>
        Number(x.peer_character_id) === cid ? { ...x, online } : x,
      )
    companions.value = patch(companions.value)
    vessels.value = patch(vessels.value)
    companionIncoming.value = patch(companionIncoming.value)
    companionOutgoing.value = patch(companionOutgoing.value)
    if (myMaster.value && Number(myMaster.value.peer_character_id) === cid) {
      myMaster.value = { ...myMaster.value, online }
    }
  }

  return {
    companions,
    vessels,
    myMaster,
    companionIncoming,
    companionOutgoing,
    companionCount,
    vesselCount,
    maxCompanions,
    maxVessels,
    vesselInviteEnabled,
    vesselHintZh,
    lastMessage,
    loading,
    refresh,
    applyPush,
    applyByName,
    applyByCharacterId,
    accept,
    reject,
    remove,
    applyPresence,
  }
})
