/**
 * M5 世界环境 Pinia store：权威时辰/天气轮询与可见性校准。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchWorldEnv } from '../api/world'
import type {
  ShichenId,
  WorldEnvHints,
  WorldEnvPublic,
  WorldWeatherId,
} from '../types/world'
import type { IdleEnvBundle } from '../types/idleEnv'
import { formatShichenCountdown } from '../utils/shichenLabel'
import { resolveWeatherId, weatherLabel } from '../utils/weatherIcon'

/** 轮询间隔；默认 5s */
function worldPollMs(): number {
  const raw = import.meta.env.VITE_WORLD_POLL_MS
  const parsed = raw ? Number(raw) : 5_000
  return Number.isFinite(parsed) && parsed >= 1_000 ? parsed : 5_000
}

/**
 * 将后端可能的嵌套/别名响应压平为 WorldEnvPublic。
 *
 * @param raw - `/world/env` data
 */
function normalizeEnv(raw: Record<string, unknown>): WorldEnvPublic {
  const cal = (raw.calendar as Record<string, unknown> | undefined) ?? {}
  const wx =
    (raw.weather_detail as Record<string, unknown> | undefined) ??
    (typeof raw.weather === 'object' && raw.weather !== null
      ? (raw.weather as Record<string, unknown>)
      : {})

  const shichen = String(
    raw.shichen ?? cal.shichen ?? cal.shichen_id ?? 'noon',
  ) as ShichenId
  const shichenLabelText = String(
    raw.shichen_label ?? cal.shichen_label ?? cal.label ?? shichen,
  )
  const nextAt = String(
    raw.next_shichen_at ?? cal.next_shichen_at ?? cal.next_at ?? '',
  )

  const weatherId = (resolveWeatherId(
    (raw.weather as string | Record<string, unknown> | undefined) ?? wx,
  ) ?? 'clear') as WorldWeatherId
  const wLabel = weatherLabel(
    (raw.weather as string | Record<string, unknown> | undefined) ?? wx,
    (raw.weather_label as string | undefined) ??
      (wx.weather_label as string | undefined) ??
      (wx.label as string | undefined),
  )

  const rawHints = (raw.hints as Record<string, string> | undefined) ?? {}
  const hints: WorldEnvHints = {
    idle: rawHints.idle ?? rawHints.idle_cultivation,
    breakthrough: rawHints.breakthrough,
    craft: rawHints.craft,
    tribulation: rawHints.tribulation,
  }

  const rawCatalog = raw.catalog as WorldEnvPublic['catalog'] | undefined
  const rawIdlePreview = raw.idle_preview as IdleEnvBundle | null | undefined

  return {
    shichen,
    shichen_label: shichenLabelText,
    next_shichen_at: nextAt,
    weather: weatherId,
    weather_label: wLabel,
    weather_next_roll_at:
      String(
        raw.weather_next_roll_at ?? wx.weather_next_roll_at ?? wx.next_roll_at ?? '',
      ) || undefined,
    hints,
    calendar_enabled: raw.calendar_enabled as boolean | undefined,
    region_id:
      (raw.region_id as string | undefined) ?? (wx.region_id as string | undefined),
    catalog: rawCatalog,
    idle_preview: rawIdlePreview ?? null,
  }
}

export const useWorldStore = defineStore('world', () => {
  const env = ref<WorldEnvPublic | null>(null)
  const loading = ref(false)
  /** 驱动倒计时重算 */
  const tick = ref(0)
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let tickTimer: ReturnType<typeof setInterval> | null = null
  let visibilityHandler: (() => void) | null = null
  let lastWeatherToastAt = 0
  let lastWeatherId: string | null = null
  let pollActive = false

  const shichen = computed(() => env.value?.shichen ?? null)
  const weather = computed(() => env.value?.weather ?? null)
  const nextShichenAt = computed(() => env.value?.next_shichen_at ?? null)
  /** 世界挂机预览（无角色标签）；供本片预计前端实时计算 */
  const idlePreview = computed(() => env.value?.idle_preview ?? null)
  const hints = computed<WorldEnvHints>(() => env.value?.hints ?? {})
  const countdownLabel = computed(() => {
    void tick.value
    return formatShichenCountdown(env.value?.next_shichen_at)
  })

  /**
   * 写入权威环境；天气变化时节流 toast。
   * 挂机「本片预计」由前端用 idle_preview 实时计算，不再为此重拉角色。
   *
   * @param next - 最新 env（已压平或原始）
   */
  function applyEnv(next: WorldEnvPublic | Record<string, unknown>): void {
    const flat =
      typeof next.weather === 'string' && typeof next.shichen === 'string'
        ? (next as WorldEnvPublic)
        : normalizeEnv(next as Record<string, unknown>)
    const prevWeather = lastWeatherId
    env.value = flat
    lastWeatherId = flat.weather
    // 天气变化 toast：至少间隔 8s，避免轮询刷屏
    if (prevWeather && prevWeather !== flat.weather) {
      const now = Date.now()
      if (now - lastWeatherToastAt > 8_000) {
        lastWeatherToastAt = now
        ElMessage.info(`天气转为：${flat.weather_label || flat.weather}`)
      }
    }
  }

  /**
   * WS `world.env` 推送校准（与 HTTP poll 共用 applyEnv；由调用方节流）。
   *
   * @param payload - 推送 payload
   */
  function applyEnvPush(payload: Record<string, unknown>): void {
    applyEnv(payload)
  }

  /**
   * 拉取 /world/env 并校准。
   *
   * @returns 错误消息；成功为 null
   */
  async function calibrate(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await fetchWorldEnv()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `加载世界环境失败（code=${envelope.code}）`
      }
      applyEnv(envelope.data as WorldEnvPublic | Record<string, unknown>)
      return null
    } finally {
      loading.value = false
    }
  }

  /** 启动倒计时本地 tick（每秒） */
  function startTickClock(): void {
    stopTickClock()
    tickTimer = setInterval(() => {
      tick.value += 1
      // 到点必须拉服务器校准，禁止本地发明时辰
      const nextAt = env.value?.next_shichen_at
      if (nextAt && Date.parse(nextAt) <= Date.now()) {
        void calibrate()
      }
    }, 1_000)
  }

  function stopTickClock(): void {
    if (tickTimer !== null) {
      clearInterval(tickTimer)
      tickTimer = null
    }
  }

  /** 启动轮询 */
  function startPoll(): void {
    if (pollActive) return
    pollActive = true
    void calibrate()
    startTickClock()
    pollTimer = setInterval(() => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
        return
      }
      void calibrate()
    }, worldPollMs())

    visibilityHandler = () => {
      if (!pollActive) return
      if (document.visibilityState === 'visible') {
        void calibrate()
      }
    }
    document.addEventListener('visibilitychange', visibilityHandler)
  }

  /** 停止轮询 */
  function stopPoll(): void {
    pollActive = false
    if (pollTimer !== null) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    stopTickClock()
    if (visibilityHandler) {
      document.removeEventListener('visibilitychange', visibilityHandler)
      visibilityHandler = null
    }
  }

  function clear(): void {
    stopPoll()
    env.value = null
    lastWeatherId = null
  }

  return {
    env,
    loading,
    shichen,
    weather,
    nextShichenAt,
    idlePreview,
    hints,
    countdownLabel,
    applyEnv,
    applyEnvPush,
    calibrate,
    startPoll,
    stopPoll,
    clear,
  }
})
