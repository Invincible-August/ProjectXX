/**
 * Research Pinia store (M8 R2 technique).
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  createResearchSessionApi,
  fetchOpenResearchSessionsApi,
  fetchResearchCatalogApi,
  fetchResearchMineApi,
  fetchResearchSessionApi,
  finalizeResearchSessionApi,
  rerollResearchSessionApi,
  saveResearchDraftApi,
  submitResearchReviewApi,
} from '../api/research'
import type {
  PrivateContentPublic,
  ResearchCatalog,
  ResearchCreateRequest,
  ResearchSessionPublic,
} from '../types/research'
import { useCharacterStore } from './character'

export const useResearchStore = defineStore('research', () => {
  const catalog = ref<ResearchCatalog | null>(null)
  const session = ref<ResearchSessionPublic | null>(null)
  const openSessions = ref<ResearchSessionPublic[]>([])
  const mine = ref<PrivateContentPublic[]>([])
  const loading = ref(false)
  /** Formation designer has unsaved paint (M8 exit polish). */
  const hasUnsavedFormationDraft = ref(false)

  async function loadCatalog(): Promise<string | null> {
    const envelope = await fetchResearchCatalogApi()
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '加载研究室目录失败'
    }
    catalog.value = envelope.data
    return null
  }

  async function loadMine(): Promise<string | null> {
    const envelope = await fetchResearchMineApi()
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '加载已定稿失败'
    }
    mine.value = envelope.data.items || []
    return null
  }

  async function loadOpenSessions(): Promise<string | null> {
    const envelope = await fetchOpenResearchSessionsApi()
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '加载进行中草案失败'
    }
    openSessions.value = envelope.data.items || []
    return null
  }

  async function loadSession(sessionId: number): Promise<string | null> {
    const envelope = await fetchResearchSessionApi(sessionId)
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '加载研究室会话失败'
    }
    session.value = envelope.data
    return null
  }

  async function create(payload: ResearchCreateRequest): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await createResearchSessionApi(payload)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '创建研究室会话失败'
      }
      session.value = envelope.data
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  async function reroll(): Promise<string | null> {
    if (!session.value) return '没有进行中的会话'
    loading.value = true
    try {
      const envelope = await rerollResearchSessionApi(session.value.id)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '重投失败'
      }
      session.value = envelope.data
      return null
    } finally {
      loading.value = false
    }
  }

  async function saveDraft(blueprint: Record<string, unknown>): Promise<string | null> {
    if (!session.value) return '没有进行中的会话'
    loading.value = true
    try {
      const envelope = await saveResearchDraftApi(session.value.id, { blueprint })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '保存草案失败'
      }
      session.value = envelope.data
      return null
    } finally {
      loading.value = false
    }
  }

  async function saveTalismanDraft(effectId: string): Promise<string | null> {
    if (!session.value) return '没有进行中的会话'
    loading.value = true
    try {
      const envelope = await saveResearchDraftApi(session.value.id, { effect_id: effectId })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '保存草案失败'
      }
      session.value = envelope.data
      return null
    } finally {
      loading.value = false
    }
  }

  async function finalize(labelZh: string): Promise<string | null> {
    if (!session.value) return '没有进行中的会话'
    loading.value = true
    try {
      const envelope = await finalizeResearchSessionApi(session.value.id, labelZh)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '定稿失败'
      }
      session.value = envelope.data
      await loadMine()
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  async function submitReview(): Promise<string | null> {
    if (!session.value) return '没有进行中的会话'
    const envelope = await submitResearchReviewApi(session.value.id)
    return envelope.message || '审核池尚未开放'
  }

  function clearSession(): void {
    session.value = null
    hasUnsavedFormationDraft.value = false
  }

  return {
    catalog,
    session,
    openSessions,
    mine,
    loading,
    hasUnsavedFormationDraft,
    loadCatalog,
    loadMine,
    loadOpenSessions,
    loadSession,
    create,
    reroll,
    saveDraft,
    saveTalismanDraft,
    finalize,
    submitReview,
    clearSession,
  }
})
