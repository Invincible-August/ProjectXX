/**
 * M7 L7 双修 Pinia store。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  cancelDual,
  confirmDual,
  fetchDualMe,
  fetchDualRanks,
  inviteDual,
  rollDual,
  setDualGender,
  settleDual,
} from '../api/dualCultivation'
import type {
  DualDiceSnapshot,
  DualGender,
  DualMePayload,
  DualRanksPayload,
  DualSession,
  DualTechnique,
} from '../types/dualCultivation'
import { useCharacterStore } from './character'

export const useDualCultivationStore = defineStore('dualCultivation', () => {
  const me = ref<DualMePayload | null>(null)
  const session = ref<DualSession | null>(null)
  const techniques = ref<DualTechnique[]>([])
  const lastDice = ref<DualDiceSnapshot | null>(null)
  const ranks = ref<DualRanksPayload | null>(null)
  const lastMessage = ref('')
  const loading = ref(false)

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
      return null
    } finally {
      loading.value = false
    }
  }

  async function chooseGender(gender: DualGender): Promise<string | null> {
    const envelope = await setDualGender(gender)
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '补选性别失败'
    }
    me.value = envelope.data
    session.value = envelope.data.session
    lastMessage.value = '道途阴阳已定'
    await useCharacterStore().fetchMe()
    return null
  }

  async function invite(
    techniqueId: string,
    targetName: string,
  ): Promise<string | null> {
    const envelope = await inviteDual({
      technique_id: techniqueId,
      target_name: targetName.trim(),
    })
    if (envelope.code !== 0) {
      return envelope.message || '邀约失败'
    }
    lastMessage.value = envelope.data?.message || '邀约已发送'
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

  async function roll(sessionId: number): Promise<string | null> {
    const envelope = await rollDual(sessionId)
    if (envelope.code !== 0) return envelope.message || '掷骰失败'
    lastMessage.value = envelope.data?.message || '掷骰完成'
    lastDice.value = (envelope.data?.dice as DualDiceSnapshot) || null
    await refreshMe()
    return null
  }

  async function settle(sessionId: number): Promise<string | null> {
    const envelope = await settleDual(sessionId)
    if (envelope.code !== 0) return envelope.message || '结算失败'
    lastMessage.value = envelope.data?.message || '双修已结算'
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
    const envelope = await fetchDualRanks(board ? { board } : undefined)
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '加载四榜失败'
    }
    ranks.value = envelope.data
    return null
  }

  return {
    me,
    session,
    techniques,
    lastDice,
    ranks,
    lastMessage,
    loading,
    refreshMe,
    chooseGender,
    invite,
    confirm,
    roll,
    settle,
    cancel,
    loadRanks,
  }
})
