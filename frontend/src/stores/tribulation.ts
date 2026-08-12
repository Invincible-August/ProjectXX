/**
 * M5 渡劫 Pinia store：会话加载 / 准备 / 开渡 / 批次。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  autoResolve,
  beginTribulation,
  commitPrep,
  fetchTribulation,
  resolveBatch,
  savePrep,
  startPrep,
  veilCheck,
} from '../api/tribulation'
import type {
  TribulationBatchEvent,
  TribulationPrepPayload,
  TribulationSessionPublic,
} from '../types/tribulation'
import { normalizeTribulationSession } from '../utils/normalizeTribulationSession'
import { useCharacterStore } from './character'

export const useTribulationStore = defineStore('tribulation', () => {
  const session = ref<TribulationSessionPublic | null>(null)
  const loading = ref(false)
  const lastEvents = ref<TribulationBatchEvent[]>([])
  const lastMessage = ref('')

  const phase = computed(() => session.value?.phase ?? null)
  const isPreparing = computed(
    () => session.value?.phase === 'preparing' || session.value?.phase === 'committed',
  )
  const isRunning = computed(() => session.value?.phase === 'running')
  const isFinished = computed(() => {
    const p = session.value?.phase
    return p === 'won' || p === 'failed' || p === 'fallen'
  })

  /** 写入会话；若带 character 则同步权威态 */
  function applySession(
    next: TribulationSessionPublic | Record<string, unknown> | null,
    character?: Parameters<ReturnType<typeof useCharacterStore>['applyCharacter']>[0],
  ): void {
    session.value = next ? normalizeTribulationSession(next) : null
    if (character) {
      useCharacterStore().applyCharacter(character)
    }
  }

  /**
   * 拉取当前渡劫会话。
   *
   * @returns 错误消息；成功为 null
   */
  async function load(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await fetchTribulation()
      if (envelope.code !== 0) {
        return envelope.message || `加载渡劫失败（code=${envelope.code}）`
      }
      // data 形如 { session: ... | null }
      session.value = normalizeTribulationSession(envelope.data)
      return null
    } finally {
      loading.value = false
    }
  }

  /** 创建准备会话（突破分流后） */
  async function start(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await startPrep()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `开启渡劫准备失败（code=${envelope.code}）`
      }
      applySession(envelope.data.session, envelope.data.character)
      lastMessage.value = envelope.data.message || ''
      return null
    } finally {
      loading.value = false
    }
  }

  /** 保存准备格 */
  async function save(payload: TribulationPrepPayload): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await savePrep(payload)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `保存准备失败（code=${envelope.code}）`
      }
      applySession(envelope.data.session, envelope.data.character)
      return null
    } finally {
      loading.value = false
    }
  }

  /** 确认准备 */
  async function commit(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await commitPrep()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `确认准备失败（code=${envelope.code}）`
      }
      applySession(envelope.data.session, envelope.data.character)
      return null
    } finally {
      loading.value = false
    }
  }

  /** 遮天检定 */
  async function runVeil(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await veilCheck()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `遮天检定失败（code=${envelope.code}）`
      }
      applySession(envelope.data.session, envelope.data.character)
      const outcome = envelope.data.veil_outcome
      const fail = envelope.data.veil_fail_effect
      if (outcome === 'success' || envelope.data.success) {
        lastMessage.value = envelope.data.message || '遮天成功：威力降档'
      } else if (fail?.label) {
        lastMessage.value = `遮天失败：${fail.label}`
      } else {
        lastMessage.value = envelope.data.message || '遮天失败'
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /** 开渡 */
  async function begin(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await beginTribulation()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `开渡失败（code=${envelope.code}）`
      }
      applySession(envelope.data.session, envelope.data.character)
      lastEvents.value = envelope.data.events ?? []
      lastMessage.value = envelope.data.message || ''
      return null
    } finally {
      loading.value = false
    }
  }

  /** 结算下一批 */
  async function wave(batchSize?: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await resolveBatch(
        batchSize != null ? { batch_size: batchSize } : undefined,
      )
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `批次结算失败（code=${envelope.code}）`
      }
      applySession(envelope.data.session, envelope.data.character)
      lastEvents.value = envelope.data.events ?? []
      lastMessage.value = envelope.data.message || ''
      return null
    } finally {
      loading.value = false
    }
  }

  /** 一键跳过到结束 */
  async function skipToEnd(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await autoResolve()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `一键结算失败（code=${envelope.code}）`
      }
      applySession(envelope.data.session, envelope.data.character)
      lastEvents.value = envelope.data.events ?? []
      lastMessage.value = envelope.data.message || ''
      return null
    } finally {
      loading.value = false
    }
  }

  function clear(): void {
    session.value = null
    lastEvents.value = []
    lastMessage.value = ''
  }

  return {
    session,
    loading,
    lastEvents,
    lastMessage,
    phase,
    isPreparing,
    isRunning,
    isFinished,
    applySession,
    load,
    start,
    save,
    commit,
    runVeil,
    begin,
    wave,
    skipToEnd,
    clear,
  }
})
