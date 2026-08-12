/**
 * M6 世界事件骨架 Pinia store（极简）。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchCurrentEvents, registerEvent } from '../api/worldEvents'
import type { WorldEventPublic } from '../types/worldEvents'

export const useWorldEventsStore = defineStore('worldEvents', () => {
  const events = ref<WorldEventPublic[]>([])
  const note = ref('')
  const loading = ref(false)
  const lastMessage = ref('')

  async function refresh(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await fetchCurrentEvents()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `加载世界事件失败（code=${envelope.code}）`
      }
        events.value = envelope.data.events ?? []
        note.value = envelope.data.note || envelope.data.hint || ''
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 报名占位。
   *
   * @param eventId - 事件 id
   */
  async function register(eventId: string | number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await registerEvent(eventId)
      if (envelope.code !== 0) {
        return envelope.message || `报名失败（code=${envelope.code}）`
      }
      lastMessage.value = envelope.data?.message || '已报名（骨架）'
      if (envelope.data?.event) {
        const idx = events.value.findIndex((e) => e.id === envelope.data!.event!.id)
        if (idx >= 0) {
          events.value[idx] = envelope.data.event
        }
      }
      await refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    events,
    note,
    loading,
    lastMessage,
    refresh,
    register,
  }
})
