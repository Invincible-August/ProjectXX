/**
 * M6 WebSocket Pinia store：连接态 / lastError / seq / 业务分发。
 */
import { defineStore } from 'pinia'
import { computed, markRaw, ref } from 'vue'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import type { WsConnectionStatus, WsEnvelope } from '../types/ws'
import { sharedWsClient, isWsEnabled, type WsClient } from '../ws/client'
import { WsType } from '../ws/protocol'
import { useDaoLordStore } from './daoLord'
import { useWorldStore } from './world'
import router from '../router'

/**
 * RSVP 弹窗：带剩余秒数；超时自动关窗并视为弃权。
 */
async function promptContestRsvp(opts: {
  isLord: boolean
  phaseEndsAt?: string | null
  rsvpSeconds?: number
}): Promise<'accept' | 'decline' | 'timeout' | 'dismiss'> {
  const endsMs = opts.phaseEndsAt
    ? Date.parse(opts.phaseEndsAt)
    : Date.now() + (opts.rsvpSeconds || 60) * 1000
  const baseMsg = opts.isLord
    ? '道主之争已经开始，是否亲自前往擂台应战？点「否」将以防守快照出战（不弃位）。'
    : '道主之争已经开始，是否前往擂台？点「否」视为弃权。'

  const remaining = (): number =>
    Math.max(0, Math.ceil((endsMs - Date.now()) / 1000))

  // 用对象承载结果，避免 await 期间定时器写入不被 TS 控制流分析识别
  const outcome: {
    settled: 'accept' | 'decline' | 'timeout' | 'dismiss' | null
  } = { settled: null }
  const timer = window.setInterval(() => {
    const left = remaining()
    const el = document.querySelector('.el-message-box__message')
    if (el) {
      el.textContent = `${baseMsg}\n\n剩余 ${left} 秒（超时视为${opts.isLord ? '快照应战' : '弃权'}）`
    }
    if (left <= 0 && outcome.settled == null) {
      outcome.settled = 'timeout'
      ElMessageBox.close()
    }
  }, 250)

  try {
    await ElMessageBox.confirm(
      `${baseMsg}\n\n剩余 ${remaining()} 秒（超时视为${opts.isLord ? '快照应战' : '弃权'}）`,
      '道主之争',
      {
        confirmButtonText: '前往擂台',
        cancelButtonText: opts.isLord ? '快照应战' : '弃权',
        type: 'warning',
        distinguishCancelAndClose: true,
        closeOnClickModal: false,
        closeOnPressEscape: false,
      },
    )
    outcome.settled = 'accept'
  } catch (e) {
    if (outcome.settled === 'timeout') {
      // already set by timer
    } else if (e === 'cancel') {
      outcome.settled = 'decline'
    } else {
      outcome.settled = 'dismiss'
    }
  } finally {
    window.clearInterval(timer)
  }

  const settled = outcome.settled

  if (settled == null) {
    return remaining() <= 0 ? 'timeout' : 'dismiss'
  }
  return settled
}

export const useWsStore = defineStore('ws', () => {
  const status = ref<WsConnectionStatus>('idle')
  const lastError = ref('')
  const seq = ref(0)
  const enabled = computed(() => isWsEnabled())

  /** markRaw：避免 Pinia/Vue 代理拆散 WsClient 私有字段 */
  const client: WsClient = markRaw(sharedWsClient)
  let wired = false
  let lastDisconnectToastAt = 0

  /** 业务信封订阅（页面可再挂） */
  const businessHandlers = new Set<(e: WsEnvelope) => void>()

  /**
   * 订阅业务信封（不含 pong）。
   *
   * @param handler - 回调
   */
  function subscribe(handler: (e: WsEnvelope) => void): () => void {
    businessHandlers.add(handler)
    return () => {
      businessHandlers.delete(handler)
    }
  }

  function wireOnce(): void {
    if (wired) return
    wired = true
    client.onStatus((next, detail) => {
      status.value = next as WsConnectionStatus
      if (detail) lastError.value = detail
      seq.value = client.seq
      if (next === 'open') {
        void import('./gameLog').then(({ useGameLogStore }) => {
          useGameLogStore().announceRealmLinked()
        })
      }
      if (next === 'reconnecting' || (next === 'closed' && detail)) {
        const now = Date.now()
        if (now - lastDisconnectToastAt > 8_000) {
          lastDisconnectToastAt = now
          ElMessage.warning(detail || '强交互通道已断开，正在重连…')
        }
      }
      if (next === 'open' && lastDisconnectToastAt > 0) {
        ElMessage.success('强交互通道已重连')
        lastDisconnectToastAt = 0
      }
    })
    client.on((envelope) => {
      seq.value = envelope.seq || client.seq
      if (envelope.type === WsType.SYS_ERROR) {
        const p = envelope.payload as { message?: string }
        if (p?.message) {
          lastError.value = p.message
          ElMessage.error(p.message)
        }
      }
      if (envelope.type === WsType.WORLD_ENV) {
        useWorldStore().applyEnvPush(
          envelope.payload as Record<string, unknown>,
        )
      }
      if (envelope.type === WsType.DAO_LORD_CONTEST_STATE) {
        const p = (envelope.payload || {}) as Record<string, unknown>
        const msg = String(p.message_zh || '')
        const action = String(p.action || '')
        const store = useDaoLordStore()
        void store.handleContestState(p).then(async () => {
          const contestId = Number(p.contest_id || store.contest?.contest?.id || 0)

          // 个人 RSVP 结果：全服静默（确认提示只在本端 submitRsvp 后弹出）
          if (action === 'rsvp_update') {
            return
          }

          // 仅本人 needs_rsvp 才弹窗
          const needs = Boolean(store.contest?.me?.needs_rsvp)
          if (
            needs &&
            contestId &&
            store.rsvpPromptedContestId !== contestId
          ) {
            store.rsvpPromptedContestId = contestId
            const isLord = Boolean(store.contest?.me?.is_lord_rsvp)
            const decision = await promptContestRsvp({
              isLord,
              phaseEndsAt:
                store.contest?.contest?.phase_ends_at ||
                String(p.phase_ends_at || ''),
              rsvpSeconds: Number(
                store.contest?.contest?.rsvp_seconds || p.rsvp_seconds || 60,
              ),
            })
            if (decision === 'accept') {
              const err = await store.submitRsvp(true)
              if (err) {
                ElMessage.error(err)
                return
              }
              ElMessage.success(store.lastMessage || '已确认前往擂台')
              await router.push({ path: '/dao-lord/arena' })
            } else if (decision === 'decline' || decision === 'timeout') {
              const err = await store.submitRsvp(false)
              if (err) ElMessage.error(err)
              else {
                ElMessage.info(
                  decision === 'timeout'
                    ? isLord
                      ? '超时未确认，将以防守快照应战'
                      : '超时未确认，已视为弃权'
                    : isLord
                      ? '将以防守快照应战'
                      : '已弃权',
                )
              }
            }
            // dismiss（点 X）：等服务端 60s 超时处理
            return
          }

          if (!msg) return

          const path = String(router.currentRoute.value.path || '')
          const onArena = path.includes('/dao-lord/arena')
          const onDaoLord = path.includes('/dao-lord')
          if (onArena || onDaoLord) {
            ElMessage.info(msg)
          } else if (p.status !== 'cancelled') {
            ElNotification({
              title: '道主之争',
              message: `${msg}（点击前往擂台）`,
              type: 'success',
              duration: 12_000,
              onClick: () => {
                void router.push({ path: '/dao-lord/arena' })
              },
            })
          } else {
            ElNotification({
              title: '道主之争',
              message: msg,
              type: 'warning',
              duration: 8_000,
            })
          }
        })
      }
      for (const h of businessHandlers) {
        try {
          h(envelope)
        } catch {
          // ignore
        }
      }
    })
  }

  function connect(): void {
    wireOnce()
    if (!enabled.value) {
      status.value = 'closed'
      return
    }
    client.connect()
  }

  function disconnect(): void {
    client.disconnect()
  }

  /** 手动重连（状态徽标点按） */
  function reconnect(): void {
    wireOnce()
    if (!enabled.value) return
    client.reconnect()
  }

  return {
    status,
    lastError,
    seq,
    enabled,
    client,
    connect,
    disconnect,
    reconnect,
    subscribe,
  }
})
