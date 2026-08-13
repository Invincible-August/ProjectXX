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
  rejectMentor,
  setDirectDisciples,
  studyTechnique,
  teachItem,
  teachLesson,
} from '../api/mentor'
import type {
  MentorBondItem,
  MentorDailyState,
  MentorLineage,
  MentorQuestItem,
  MentorTeachingOptions,
  MentorTransmissionItem,
} from '../types/mentor'

export const useMentorStore = defineStore('mentor', () => {
  const bond = ref<MentorBondItem | null>(null)
  const incoming = ref<MentorBondItem[]>([])
  const outgoing = ref<MentorBondItem[]>([])
  const quests = ref<MentorQuestItem[]>([])
  const daily = ref<MentorDailyState | null>(null)
  const options = ref<MentorTeachingOptions | null>(null)
  const transmissions = ref<MentorTransmissionItem[]>([])
  const lineage = ref<MentorLineage | null>(null)
  const channelRef = ref<string | null>(null)
  const loading = ref(false)
  const lastMessage = ref('')
  const lastLogLines = ref<string[]>([])
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
      daily.value = envelope.data.daily
      options.value = envelope.data.options
      transmissions.value = envelope.data.transmissions ?? []
      lineage.value = envelope.data.lineage ?? null
      channelRef.value = envelope.data.channel_ref
      if (envelope.data.auto_graduate_message) {
        lastMessage.value = envelope.data.auto_graduate_message
        lastLogLines.value = [envelope.data.auto_graduate_message]
      }
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

  async function lesson(body: {
    kind: 'dao' | 'craft' | 'technique'
    resource?: 'spirit' | 'body' | null
    target_id?: string | null
  }): Promise<string | null> {
    const envelope = await teachLesson(body)
    if (envelope.code !== 0) return envelope.message || '日课失败'
    lastMessage.value = envelope.data?.message || '日课完成'
    await refresh()
    return null
  }

  async function teach(body: {
    item_kind: 'technique' | 'recipe'
    item_id: string
  }): Promise<string | null> {
    const envelope = await teachItem(body)
    if (envelope.code !== 0) return envelope.message || '传授失败'
    lastMessage.value = envelope.data?.message || '传授进度已更新'
    await refresh()
    return null
  }

  async function study(techniqueId: string): Promise<string | null> {
    const envelope = await studyTechnique({ technique_id: techniqueId })
    if (envelope.code !== 0) return envelope.message || '请学失败'
    lastMessage.value = envelope.data?.message || '请学进度已更新'
    await refresh()
    return null
  }

  async function setDirect(apprenticeCharacterIds: number[]): Promise<string | null> {
    const envelope = await setDirectDisciples({
      apprentice_character_ids: apprenticeCharacterIds,
    })
    if (envelope.code !== 0) return envelope.message || '设置亲传失败'
    const lines =
      envelope.data?.log_lines && envelope.data.log_lines.length
        ? envelope.data.log_lines
        : [envelope.data?.message || '亲传已更新']
    lastLogLines.value = lines
    lastMessage.value = lines.join('；')
    await refresh()
    return null
  }

  async function graduate(): Promise<string | null> {
    const envelope = await graduateMentor()
    if (envelope.code !== 0) return envelope.message || '出师失败'
    const data = envelope.data as { message?: string; log_lines?: string[] } | undefined
    const lines =
      data?.log_lines && data.log_lines.length
        ? data.log_lines
        : [data?.message || '出师成功']
    lastLogLines.value = lines
    lastMessage.value = lines.join('；')
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
    daily,
    options,
    transmissions,
    lineage,
    channelRef,
    loading,
    lastMessage,
    lastLogLines,
    lastError,
    refresh,
    apply,
    accept,
    reject,
    lesson,
    teach,
    study,
    setDirect,
    graduate,
    dissolve,
  }
})
