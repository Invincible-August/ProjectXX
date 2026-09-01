/**
 * 游戏事件日志：按角色持久化到 localStorage。
 *
 * - 切页 / 刷新可恢复
 * - 超过 TTL（默认 24h）的条目加载时丢弃
 * - 环形缓冲最多 MAX_LOG_ENTRIES 条
 * - 登出 / 换角色时清空（clear / bindCharacter）
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { createLogEntry, type GameLogEntry, type GameLogLevel } from '../types/gameLog'

const MAX_LOG_ENTRIES = 200
/** 超过此时长的条目不再恢复（毫秒） */
const LOG_TTL_MS = 24 * 60 * 60 * 1000
const STORAGE_PREFIX = 'xiuxian.gamelog.'

interface PersistedBlob {
  characterId: number
  savedAt: number
  hallBootstrapped: boolean
  realmLinkedAnnounced: boolean
  entries: GameLogEntry[]
}

function storageKey(characterId: number): string {
  return `${STORAGE_PREFIX}${characterId}`
}

function normalizeEntry(raw: unknown): GameLogEntry | null {
  if (!raw || typeof raw !== 'object') return null
  const row = raw as Record<string, unknown>
  const message = String(row.message || '').trim()
  if (!message) return null
  const levelRaw = String(row.level || 'info')
  const level: GameLogLevel =
    levelRaw === 'success' || levelRaw === 'warning' || levelRaw === 'system'
      ? levelRaw
      : 'info'
  const ts = Number(row.ts || 0) || Date.now()
  const id = String(row.id || `${ts}-${Math.random().toString(36).slice(2, 8)}`)
  const time =
    typeof row.time === 'string' && row.time
      ? row.time
      : (() => {
          const d = new Date(ts)
          const pad = (n: number) => String(n).padStart(2, '0')
          return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
        })()
  return { id, time, ts, message, level }
}

function pruneEntries(list: GameLogEntry[], now = Date.now()): GameLogEntry[] {
  const cutoff = now - LOG_TTL_MS
  const kept = list.filter((e) => (e.ts || 0) >= cutoff)
  return kept.length > MAX_LOG_ENTRIES ? kept.slice(-MAX_LOG_ENTRIES) : kept
}

function readPersisted(characterId: number): PersistedBlob | null {
  try {
    const raw = localStorage.getItem(storageKey(characterId))
    if (!raw) return null
    const parsed = JSON.parse(raw) as PersistedBlob
    if (!parsed || Number(parsed.characterId) !== characterId) return null
    if (Date.now() - Number(parsed.savedAt || 0) > LOG_TTL_MS) {
      localStorage.removeItem(storageKey(characterId))
      return null
    }
    const entries = pruneEntries(
      (Array.isArray(parsed.entries) ? parsed.entries : [])
        .map(normalizeEntry)
        .filter((e): e is GameLogEntry => e != null),
    )
    return {
      characterId,
      savedAt: Number(parsed.savedAt || Date.now()),
      hallBootstrapped: Boolean(parsed.hallBootstrapped),
      realmLinkedAnnounced: Boolean(parsed.realmLinkedAnnounced),
      entries,
    }
  } catch {
    return null
  }
}

function writePersisted(blob: PersistedBlob): void {
  try {
    localStorage.setItem(storageKey(blob.characterId), JSON.stringify(blob))
  } catch {
    // Quota / private mode：静默放弃，内存仍可用
  }
}

function removePersisted(characterId: number | null): void {
  if (characterId == null) return
  try {
    localStorage.removeItem(storageKey(characterId))
  } catch {
    // ignore
  }
}

export const useGameLogStore = defineStore('gameLog', () => {
  const entries = ref<GameLogEntry[]>([])
  /** 当前绑定的角色；未绑定时仍可写内存，但不落盘 */
  const boundCharacterId = ref<number | null>(null)
  /** 本登录会话是否已做过大厅首屏问候 */
  const hallBootstrapped = ref(false)
  /** 本会话是否已宣布仙界通道连通（WS open） */
  const realmLinkedAnnounced = ref(false)

  function persistNow(): void {
    const cid = boundCharacterId.value
    if (cid == null) return
    writePersisted({
      characterId: cid,
      savedAt: Date.now(),
      hallBootstrapped: hallBootstrapped.value,
      realmLinkedAnnounced: realmLinkedAnnounced.value,
      entries: pruneEntries(entries.value),
    })
  }

  /**
   * 绑定角色并恢复该角色持久化日志。
   * 换角色时先清空内存再加载新角色；同角色重复绑定为幂等。
   */
  function bindCharacter(characterId: number | null | undefined): void {
    const next =
      characterId != null && Number.isFinite(Number(characterId)) && Number(characterId) > 0
        ? Number(characterId)
        : null
    if (next === boundCharacterId.value) {
      // 同角色：若内存空则尝试补恢复（热更新 / 首次晚绑定）
      if (next != null && entries.value.length === 0) {
        const blob = readPersisted(next)
        if (blob?.entries.length) {
          entries.value = blob.entries
          hallBootstrapped.value = blob.hallBootstrapped
          realmLinkedAnnounced.value = blob.realmLinkedAnnounced
        }
      }
      return
    }
    boundCharacterId.value = next
    if (next == null) {
      entries.value = []
      hallBootstrapped.value = false
      realmLinkedAnnounced.value = false
      return
    }
    const blob = readPersisted(next)
    if (blob) {
      entries.value = blob.entries
      hallBootstrapped.value = blob.hallBootstrapped
      realmLinkedAnnounced.value = blob.realmLinkedAnnounced
    } else {
      entries.value = []
      hallBootstrapped.value = false
      realmLinkedAnnounced.value = false
    }
  }

  /**
   * 追加一条日志（环形缓冲 + 落盘）。
   */
  function push(message: string, level: GameLogLevel = 'info'): void {
    const text = String(message || '').trim()
    if (!text) return
    const next = pruneEntries([...entries.value, createLogEntry(text, level)])
    entries.value = next
    persistNow()
  }

  /** 标记大厅首屏引导已完成 */
  function markHallBootstrapped(): void {
    hallBootstrapped.value = true
    persistNow()
  }

  /** 通道首次连通时写一条系统日志（幂等）。 */
  function announceRealmLinked(): void {
    if (realmLinkedAnnounced.value) return
    realmLinkedAnnounced.value = true
    push('仙界通道已连通（长连接保持至离开玩法）', 'system')
  }

  /** 清空内存与当前角色的持久化（登出时） */
  function clear(): void {
    removePersisted(boundCharacterId.value)
    boundCharacterId.value = null
    entries.value = []
    hallBootstrapped.value = false
    realmLinkedAnnounced.value = false
  }

  return {
    entries,
    boundCharacterId,
    hallBootstrapped,
    realmLinkedAnnounced,
    bindCharacter,
    push,
    markHallBootstrapped,
    announceRealmLinked,
    clear,
  }
})
