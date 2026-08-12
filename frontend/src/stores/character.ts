/**
 * 角色 Pinia store：权威面板 + 修炼实时预测 / tick 对齐拉取（M1.5）。
 *
 * - character：服务端权威（突破/战斗/禁战只读此对象）
 * - display*：客户端预测，供角色面板 + IdlePanel 片内进度条
 * - startIdleRealtime：按 next_tick_at 对齐 sync，无固定 5s 打满
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { createCharacterApi, fetchMyCharacterApi } from '../api/character'
import { setIdleDirectionApi, syncIdleApi, claimOfflineApi } from '../api/idle'
import type { CharacterPublic } from '../types/character'
import type { IdleDirection, IdleSyncData } from '../types/idle'
import { validateCharacterName } from '../utils/characterName'
import {
  isIdleBusyDirection,
  isProductiveDirection,
  predictAvatarIdleDisplay,
  predictIdleDisplay,
  resolveNextDueMs,
  type IdleDisplaySnapshot,
} from '../utils/idlePredict'
import { computeTickGainForDirection } from '../utils/idleRateClient'
import { useAuthStore } from './auth'
import { useWorldStore } from './world'

/** 兜底最大对表间隔（防定时器漂移）；默认 120s */
function maxReconcileMs(): number {
  const raw = import.meta.env.VITE_IDLE_POLL_MS
  const parsed = raw ? Number(raw) : 120_000
  return Number.isFinite(parsed) && parsed >= 5_000 ? parsed : 120_000
}

/** 预测刷新间隔；默认 250ms（仅驱动片内进度条，不增加 HTTP） */
function predictIntervalMs(): number {
  const raw = import.meta.env.VITE_IDLE_PREDICT_MS
  const parsed = raw ? Number(raw) : 250
  return Number.isFinite(parsed) && parsed >= 100 ? parsed : 250
}

/** 雷群抖动上限 ms */
const JITTER_MS = 2_000

export const useCharacterStore = defineStore('character', () => {
  const character = ref<CharacterPublic | null>(null)
  const loading = ref(false)
  /** sync 进行中防叠（单飞） */
  const pollingInFlight = ref(false)
  /** 服务端下发的下一 tick；方向切换/sync 后更新 */
  const nextTickAt = ref<string | null>(null)
  /** 预测展示时钟触发用 */
  const displayTick = ref(0)

  let syncTimer: ReturnType<typeof setTimeout> | null = null
  let predictTimer: ReturnType<typeof setInterval> | null = null
  let reconcileTimer: ReturnType<typeof setTimeout> | null = null
  let visibilityHandler: (() => void) | null = null
  let onSettledCb: ((data: IdleSyncData) => void) | null = null
  let realtimeActive = false

  /**
   * 刷新预测时钟（驱动 computed 重算）。
   */
  function bumpDisplay(): void {
    displayTick.value += 1
  }

  /**
   * 本体挂机面板展示快照（只读预测；不污染权威 character）。
   * 池增量用浏览器实时环境速率，与「本周天预计」一致。
   */
  const display = computed<IdleDisplaySnapshot | null>(() => {
    void displayTick.value
    if (!character.value) return null
    const world = useWorldStore()
    const envRate = computeTickGainForDirection(
      character.value,
      world.idlePreview,
      world.shichen,
      world.weather,
    )
    return predictIdleDisplay(character.value, Date.now(), envRate)
  })

  /**
   * 化身挂机面板展示快照（与本体共用 predict 时钟；无化身时为 null）。
   */
  const avatarDisplay = computed<IdleDisplaySnapshot | null>(() => {
    void displayTick.value
    if (!character.value?.has_avatar) return null
    return predictAvatarIdleDisplay(character.value, Date.now())
  })

  /**
   * 各玩法 API 返回的 character 统一写入权威态。
   *
   * @param ch - 最新角色
   * @param serverNextTickAt - 可选 idle 响应中的 next_tick_at
   */
  function applyCharacter(
    ch: CharacterPublic,
    serverNextTickAt?: string | null,
  ): void {
    character.value = ch
    useAuthStore().setHasCharacter(true)
    if (serverNextTickAt !== undefined) {
      nextTickAt.value = serverNextTickAt
    } else if (
      !isIdleBusyDirection(ch.idle_direction) ||
      (isProductiveDirection(ch.idle_direction) && ch.is_stalled) ||
      ch.offline_pending
    ) {
      nextTickAt.value = null
    } else {
      // 无服务端提示时由本地推算
      const due = resolveNextDueMs(ch, null)
      nextTickAt.value = due ? new Date(due).toISOString() : null
    }
    bumpDisplay()
    if (realtimeActive) {
      if (ch.offline_pending) {
        // pending：停 sync / 预测时钟，避免无意义 250ms 刷新与误入账
        clearSyncTimers()
        stopPredictClock()
      } else {
        if (predictTimer === null) {
          startPredictClock()
        }
        scheduleSyncAligned()
      }
    }
  }

  /**
   * 拉取我的角色：GET /characters/me。
   *
   * @returns 是否成功拿到角色（无角色返回 false，不抛业务码 40005）
   */
  async function fetchMe(): Promise<boolean> {
    loading.value = true
    try {
      const envelope = await fetchMyCharacterApi()
      if (envelope.code === 0 && envelope.data) {
        applyCharacter(envelope.data)
        return true
      }
      if (envelope.code === 40005) {
        character.value = null
        nextTickAt.value = null
        useAuthStore().setHasCharacter(false)
        return false
      }
      throw new Error(envelope.message || `获取角色失败（code=${envelope.code}）`)
    } finally {
      loading.value = false
    }
  }

  /**
   * 创建角色：校验名字 → POST /characters → 更新 auth。
   *
   * @param name - 用户输入的角色名
   * @param gender - 道途阴阳 male|female
   */
  async function create(
    name: string,
    gender: 'male' | 'female',
  ): Promise<CharacterPublic> {
    const nameError = validateCharacterName(name)
    if (nameError) {
      throw new Error(nameError)
    }
    if (gender !== 'male' && gender !== 'female') {
      throw new Error('请选择道途阴阳（性别）')
    }
    const trimmed = name.trim()
    const auth = useAuthStore()
    if (!auth.user?.id) {
      throw new Error('未登录，无法创建角色')
    }

    loading.value = true
    try {
      const envelope = await createCharacterApi({ name: trimmed, gender })
      if (envelope.code !== 0 || !envelope.data) {
        const err = new Error(
          envelope.message || `创建角色失败（code=${envelope.code}）`,
        ) as Error & { code?: number }
        err.code = envelope.code
        throw err
      }
      applyCharacter(envelope.data)
      return envelope.data
    } finally {
      loading.value = false
    }
  }

  /**
   * 空结算占位（单飞冲突时）。
   */
  function emptySyncFromLocal(): IdleSyncData {
    if (!character.value) {
      throw new Error('角色未加载')
    }
    return {
      character: character.value,
      settled_ticks: 0,
      gained_cultivation: 0,
      spent_spirit_stones: 0,
      next_tick_at: nextTickAt.value,
    }
  }

  /**
   * 立即 sync 一次；返回结算摘要（供日志 / 对齐调度）。
   */
  async function syncNow(): Promise<IdleSyncData> {
    if (pollingInFlight.value) {
      return emptySyncFromLocal()
    }
    pollingInFlight.value = true
    try {
      const envelope = await syncIdleApi()
      if (envelope.code !== 0 || !envelope.data) {
        throw new Error(envelope.message || `同步失败（code=${envelope.code}）`)
      }
      applyCharacter(envelope.data.character, envelope.data.next_tick_at ?? null)
      return envelope.data
    } finally {
      pollingInFlight.value = false
    }
  }

  /**
   * 切换修炼方向。
   *
   * @param direction - 目标方向
   */
  async function setDirection(direction: IdleDirection): Promise<IdleSyncData> {
    const envelope = await setIdleDirectionApi(direction)
    if (envelope.code !== 0 || !envelope.data) {
      const err = new Error(
        envelope.message || `切换修炼失败（code=${envelope.code}）`,
      ) as Error & { code?: number }
      err.code = envelope.code
      throw err
    }
    applyCharacter(envelope.data.character, envelope.data.next_tick_at ?? null)
    return envelope.data
  }

  /**
   * 领取离线 pending；成功后恢复 tick 对齐调度。
   */
  async function claimOffline(): Promise<IdleSyncData> {
    const envelope = await claimOfflineApi()
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || `领取离线失败（code=${envelope.code}）`)
    }
    applyCharacter(
      envelope.data.character,
      envelope.data.next_tick_at ?? null,
    )
    return {
      character: envelope.data.character,
      settled_ticks: envelope.data.applied.settled_ticks,
      gained_cultivation: envelope.data.applied.gained_cultivation,
      gained_body: envelope.data.applied.gained_body,
      gained_crafting: envelope.data.applied.gained_crafting,
      spent_spirit_stones: envelope.data.applied.spent_spirit_stones,
      next_tick_at: envelope.data.next_tick_at ?? null,
    }
  }

  /**
   * 是否有未领取离线收益。
   */
  const hasOfflinePending = computed(
    () => Boolean(character.value?.offline_pending),
  )

  /**
   * 清除 sync / reconcile 定时器（预测时钟单独管）。
   */
  function clearSyncTimers(): void {
    if (syncTimer !== null) {
      clearTimeout(syncTimer)
      syncTimer = null
    }
    if (reconcileTimer !== null) {
      clearTimeout(reconcileTimer)
      reconcileTimer = null
    }
  }

  /**
   * 可见且修灵中时执行 sync；忽略网络错误。
   */
  async function runAlignedSync(): Promise<void> {
    if (!realtimeActive) return
    if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
      return
    }
    const ch = character.value
    if (
      !ch ||
      !isIdleBusyDirection(ch.idle_direction) ||
      (isProductiveDirection(ch.idle_direction) && ch.is_stalled) ||
      ch.offline_pending
    ) {
      scheduleSyncAligned()
      return
    }
    try {
      const data = await syncNow()
      const hasMining =
        Number(data.gained_mining_stones || 0) > 0 ||
        Number(data.spent_stamina || 0) > 0 ||
        Number(data.mining_pool_stones || 0) > 0
      if ((data.settled_ticks > 0 || hasMining) && onSettledCb) {
        onSettledCb(data)
      }
    } catch {
      // 失败后稍后重试，避免死循环打爆
      if (realtimeActive) {
        syncTimer = setTimeout(() => {
          syncTimer = null
          void runAlignedSync()
        }, 5_000 + Math.floor(Math.random() * JITTER_MS))
      }
      return
    }
    scheduleSyncAligned()
  }

  /**
   * 按 next_tick_at / 本地推算排下一拍 sync；未修炼/停滞则不拉。
   */
  function scheduleSyncAligned(): void {
    clearSyncTimers()
    if (!realtimeActive) return

    const ch = character.value
    if (
      !ch ||
      !isIdleBusyDirection(ch.idle_direction) ||
      (isProductiveDirection(ch.idle_direction) && ch.is_stalled) ||
      ch.offline_pending
    ) {
      return
    }
    if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
      return
    }

    const dueMs = resolveNextDueMs(ch, nextTickAt.value)
    if (dueMs == null) return

    const jitter = Math.floor(Math.random() * JITTER_MS)
    const delay = Math.max(0, dueMs - Date.now()) + jitter
    syncTimer = setTimeout(() => {
      syncTimer = null
      void runAlignedSync()
    }, delay)

    // 兜底：最长 maxReconcileMs 强制对表一次
    reconcileTimer = setTimeout(() => {
      reconcileTimer = null
      void runAlignedSync()
    }, maxReconcileMs() + jitter)
  }

  /**
   * 启动预测时钟（默认约 250ms bump，驱动片内进度条）。
   */
  function startPredictClock(): void {
    stopPredictClock()
    bumpDisplay()
    predictTimer = setInterval(() => {
      bumpDisplay()
    }, predictIntervalMs())
  }

  function stopPredictClock(): void {
    if (predictTimer !== null) {
      clearInterval(predictTimer)
      predictTimer = null
    }
  }

  /**
   * 启动大厅修炼实时：预测展示 + tick 对齐拉取。
   *
   * @param onSettled - 权威结算有 ticks 时回调写日志
   */
  function startIdleRealtime(
    onSettled?: (data: IdleSyncData) => void,
  ): void {
    stopIdleRealtime()
    realtimeActive = true
    onSettledCb = onSettled ?? null
    startPredictClock()
    scheduleSyncAligned()

    visibilityHandler = () => {
      if (!realtimeActive) return
      if (document.visibilityState === 'visible') {
        const dueMs = resolveNextDueMs(character.value, nextTickAt.value)
        if (dueMs != null && dueMs <= Date.now()) {
          void runAlignedSync()
        } else {
          scheduleSyncAligned()
        }
        bumpDisplay()
      } else {
        clearSyncTimers()
      }
    }
    document.addEventListener('visibilitychange', visibilityHandler)
  }

  /** @deprecated 使用 startIdleRealtime；保留别名兼容 */
  function startPolling(onSettled?: (data: IdleSyncData) => void): void {
    startIdleRealtime(onSettled)
  }

  /** 停止实时调度与预测时钟。 */
  function stopIdleRealtime(): void {
    realtimeActive = false
    onSettledCb = null
    clearSyncTimers()
    stopPredictClock()
    if (visibilityHandler) {
      document.removeEventListener('visibilitychange', visibilityHandler)
      visibilityHandler = null
    }
  }

  /** @deprecated 使用 stopIdleRealtime */
  function stopPolling(): void {
    stopIdleRealtime()
  }

  /** 登出时清空内存中的角色并停表。 */
  function clear(): void {
    stopIdleRealtime()
    character.value = null
    nextTickAt.value = null
  }

  return {
    character,
    display,
    avatarDisplay,
    nextTickAt,
    loading,
    pollingInFlight,
    hasOfflinePending,
    applyCharacter,
    fetchMe,
    create,
    syncNow,
    setDirection,
    claimOffline,
    startIdleRealtime,
    stopIdleRealtime,
    startPolling,
    stopPolling,
    clear,
  }
})
