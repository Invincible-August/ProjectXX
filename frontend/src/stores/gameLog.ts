/**
 * 大厅游戏日志（会话级共享）：社交/大厅等页写入后，回大厅可见。
 *
 * ``hallBootstrapped``：本登录会话是否已做过大厅首屏问候，避免切页反复「正在连接仙界…」。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { createLogEntry, type GameLogEntry, type GameLogLevel } from '../types/gameLog'

const MAX_LOG_ENTRIES = 200

export const useGameLogStore = defineStore('gameLog', () => {
  const entries = ref<GameLogEntry[]>([])
  /** 本会话是否已完成大厅首屏引导日志 */
  const hallBootstrapped = ref(false)
  /** 本会话是否已宣布仙界通道连通（WS open） */
  const realmLinkedAnnounced = ref(false)

  /**
   * 追加一条日志（环形缓冲）。
   *
   * @param message - 正文
   * @param level - 级别
   */
  function push(message: string, level: GameLogLevel = 'info'): void {
    const text = String(message || '').trim()
    if (!text) return
    const next = [...entries.value, createLogEntry(text, level)]
    entries.value =
      next.length > MAX_LOG_ENTRIES ? next.slice(-MAX_LOG_ENTRIES) : next
  }

  /** 标记大厅首屏引导已完成 */
  function markHallBootstrapped(): void {
    hallBootstrapped.value = true
  }

  /**
   * 通道首次连通时写一条系统日志（幂等）。
   */
  function announceRealmLinked(): void {
    if (realmLinkedAnnounced.value) return
    realmLinkedAnnounced.value = true
    push('仙界通道已连通（长连接保持至离开玩法）', 'system')
  }

  /** 清空本会话日志与引导标记（登出时） */
  function clear(): void {
    entries.value = []
    hallBootstrapped.value = false
    realmLinkedAnnounced.value = false
  }

  return {
    entries,
    hallBootstrapped,
    realmLinkedAnnounced,
    push,
    markHallBootstrapped,
    announceRealmLinked,
    clear,
  }
})
