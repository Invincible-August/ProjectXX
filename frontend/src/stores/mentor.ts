/**
 * M7 L6 师徒 Pinia store。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  acceptMentor,
  applyMentor,
  dissolveMentor,
  fetchMentorMe,
  graduateMentor,
  passCultivation,
  rejectMentor,
} from '../api/mentor'
import type { MentorBondItem, MentorQuestItem } from '../types/mentor'

export const useMentorStore = defineStore('mentor', () => {
  const bond = ref<MentorBondItem | null>(null)
  const incoming = ref<MentorBondItem[]>([])
  const outgoing = ref<MentorBondItem[]>([])
  const quests = ref<MentorQuestItem[]>([])
  const channelRef = ref<string | null>(null)
  const loading = ref(false)
  const lastMessage = ref('')
  const lastError = ref('')

  async function refresh(): Promise<string | null> {
    loading.value = true
    lastError.value = ''
    try {
      const envelope = await fetchMentorMe()
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `加载师徒失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      bond.value = envelope.data.bond
      incoming.value = envelope.data.incoming ?? []
      outgoing.value = envelope.data.outgoing ?? []
      quests.value = envelope.data.quests ?? []
      channelRef.value = envelope.data.channel_ref
      return null
    } finally {
      loading.value = false
    }
  }

  async function apply(
    targetName: string,
    intent: 'apprentice' | 'master',
  ): Promise<string | null> {
    const envelope = await applyMentor({ target_name: targetName, intent })
    if (envelope.code !== 0) {
      return envelope.message || `申请失败（code=${envelope.code}）`
    }
    lastMessage.value = envelope.data?.message || '申请已发送'
    await refresh()
    return null
  }

  async function accept(bondId: number): Promise<string | null> {
    const envelope = await acceptMentor(bondId)
    if (envelope.code !== 0) return envelope.message || '确认失败'
    lastMessage.value = envelope.data?.message || '已结成师徒'
    await refresh()
    return null
  }

  async function reject(bondId: number): Promise<string | null> {
    const envelope = await rejectMentor(bondId)
    if (envelope.code !== 0) return envelope.message || '拒绝失败'
    lastMessage.value = envelope.data?.message || '已拒绝'
    await refresh()
    return null
  }

  async function pass(): Promise<string | null> {
    const envelope = await passCultivation()
    if (envelope.code !== 0) return envelope.message || '传功失败'
    lastMessage.value = envelope.data?.message || '传功成功'
    await refresh()
    return null
  }

  async function graduate(): Promise<string | null> {
    const envelope = await graduateMentor()
    if (envelope.code !== 0) return envelope.message || '出师失败'
    lastMessage.value = envelope.data?.message || '出师成功'
    await refresh()
    return null
  }

  async function dissolve(): Promise<string | null> {
    const envelope = await dissolveMentor()
    if (envelope.code !== 0) return envelope.message || '解除失败'
    lastMessage.value = envelope.data?.message || '已解除'
    await refresh()
    return null
  }

  return {
    bond,
    incoming,
    outgoing,
    quests,
    channelRef,
    loading,
    lastMessage,
    lastError,
    refresh,
    apply,
    accept,
    reject,
    pass,
    graduate,
    dissolve,
  }
})
