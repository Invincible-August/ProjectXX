/**
 * M6 WebSocket 客户端：连接、鉴权首帧、心跳、指数退避重连。
 *
 * 不承担业务结算；房间 join/leave 见 rooms.ts。
 * VITE_WS_ENABLED=false 时 connect 为空操作。
 */
import { getAccessToken } from '../utils/storage'
import type { WsClientMessage, WsEnvelopeHandler } from '../types/ws'
import { coerceWsEnvelope, WsType } from './protocol'

/** 是否启用 WS（默认 true） */
export function isWsEnabled(): boolean {
  const raw = import.meta.env.VITE_WS_ENABLED
  if (raw === undefined || raw === '') return true
  return String(raw).toLowerCase() !== 'false'
}

/**
 * 解析 WS URL：优先 VITE_WS_URL；否则由 API base 推导。
 */
export function resolveWsUrl(): string {
  const explicit = import.meta.env.VITE_WS_URL as string | undefined
  if (explicit && String(explicit).trim()) return String(explicit).trim()

  const apiBase =
    (import.meta.env.VITE_API_BASE_URL as string | undefined) ||
    'http://127.0.0.1:8000/api/v1'
  try {
    const u = new URL(apiBase)
    u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'
    // apiBase 已含 /api/v1 → 追加 /ws
    const path = u.pathname.replace(/\/$/, '')
    u.pathname = path.endsWith('/ws') ? path : `${path}/ws`
    u.search = ''
    u.hash = ''
    return u.toString()
  } catch {
    return 'ws://127.0.0.1:8000/api/v1/ws'
  }
}

/** 重连基础间隔 ms */
function reconnectBaseMs(): number {
  const raw = import.meta.env.VITE_WS_RECONNECT_MS
  const parsed = raw ? Number(raw) : 2_000
  return Number.isFinite(parsed) && parsed >= 500 ? parsed : 2_000
}

const PING_INTERVAL_MS = 20_000
const MAX_RECONNECT_ATTEMPTS = 12

type StatusListener = (status: string, detail?: string) => void

/**
 * 单例式 WS 客户端（由 Pinia store 持有实例）。
 */
export class WsClient {
  private socket: WebSocket | null = null
  private handlers = new Set<WsEnvelopeHandler>()
  private statusListeners = new Set<StatusListener>()
  private pingTimer: ReturnType<typeof setInterval> | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectAttempt = 0
  private intentionalClose = false
  private lastSeq = 0
  private _status: string = 'idle'
  private _lastError = ''

  get status(): string {
    return this._status
  }

  get lastError(): string {
    return this._lastError
  }

  get seq(): number {
    return this.lastSeq
  }

  /**
   * 订阅所有入站信封。
   *
   * @param handler - 回调
   * @returns 取消订阅函数
   */
  on(handler: WsEnvelopeHandler): () => void {
    this.handlers.add(handler)
    return () => {
      this.handlers.delete(handler)
    }
  }

  /** 订阅连接态变化 */
  onStatus(listener: StatusListener): () => void {
    this.statusListeners.add(listener)
    return () => {
      this.statusListeners.delete(listener)
    }
  }

  private setStatus(next: string, detail?: string): void {
    this._status = next
    if (detail) this._lastError = detail
    for (const l of this.statusListeners) {
      try {
        l(next, detail)
      } catch {
        // 监听器异常不影响连接
      }
    }
  }

  /**
   * 建立连接；已连接则忽略。
   */
  connect(): void {
    if (!isWsEnabled()) {
      this.setStatus('closed', '强交互通道未开启')
      return
    }
    if (
      this.socket &&
      (this.socket.readyState === WebSocket.OPEN ||
        this.socket.readyState === WebSocket.CONNECTING)
    ) {
      return
    }
    this.intentionalClose = false
    this.openSocket(this.reconnectAttempt > 0 ? 'reconnecting' : 'connecting')
  }

  /** 手动重连（徽标按钮） */
  reconnect(): void {
    this.disconnect()
    this.reconnectAttempt = 0
    this.connect()
  }

  /** 主动断开且不自动重连 */
  disconnect(): void {
    this.intentionalClose = true
    this.clearReconnectTimer()
    this.stopPing()
    if (this.socket) {
      try {
        this.socket.close(1000, 'client_disconnect')
      } catch {
        // ignore
      }
      this.socket = null
    }
    this.setStatus('closed')
  }

  /**
   * 发送上行消息。
   *
   * @param message - 客户端消息
   * @returns 是否已写入套接字
   */
  send(message: WsClientMessage): boolean {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return false
    const envelope = {
      type: message.type,
      seq: message.seq ?? 0,
      ts: message.ts ?? new Date().toISOString(),
      payload: message.payload ?? {},
    }
    try {
      this.socket.send(JSON.stringify(envelope))
      return true
    } catch {
      return false
    }
  }

  private openSocket(status: string): void {
    const url = resolveWsUrl()
    this.setStatus(status)
    let socket: WebSocket
    try {
      socket = new WebSocket(url)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '无法创建 WebSocket'
      this._lastError = msg
      this.setStatus('closed', msg)
      this.scheduleReconnect()
      return
    }
    this.socket = socket

    socket.onopen = () => {
      this.reconnectAttempt = 0
      this.setStatus('open')
      // 首帧鉴权（生产偏好；DEV 也可 ?token=）
      const token = getAccessToken()
      if (token) {
        this.send({ type: WsType.AUTH, payload: { token } })
      }
      this.startPing()
    }

    socket.onmessage = (ev: MessageEvent) => {
      let parsed: unknown
      try {
        parsed = JSON.parse(String(ev.data))
      } catch {
        return
      }
      const envelope = coerceWsEnvelope(parsed)
      if (!envelope) return
      if (envelope.seq > this.lastSeq) this.lastSeq = envelope.seq
      // 心跳应答不强制业务处理
      if (envelope.type === WsType.PONG) return
      for (const h of this.handlers) {
        try {
          h(envelope)
        } catch {
          // ignore handler errors
        }
      }
    }

    socket.onerror = () => {
      this._lastError = 'WebSocket 连接异常'
    }

    socket.onclose = () => {
      this.stopPing()
      this.socket = null
      if (this.intentionalClose) {
        this.setStatus('closed')
        return
      }
      this.setStatus('reconnecting', this._lastError || '连接已断开')
      this.scheduleReconnect()
    }
  }

  private startPing(): void {
    this.stopPing()
    this.pingTimer = setInterval(() => {
      this.send({ type: WsType.PING, payload: {} })
    }, PING_INTERVAL_MS)
  }

  private stopPing(): void {
    if (this.pingTimer !== null) {
      clearInterval(this.pingTimer)
      this.pingTimer = null
    }
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private scheduleReconnect(): void {
    if (!isWsEnabled() || this.intentionalClose) return
    if (this.reconnectAttempt >= MAX_RECONNECT_ATTEMPTS) {
      this.setStatus('closed', '重连次数已达上限，请手动重连')
      return
    }
    this.clearReconnectTimer()
    const base = reconnectBaseMs()
    // 指数退避 + 轻微抖动，避免雷群
    const delay = Math.min(
      30_000,
      base * Math.pow(1.6, this.reconnectAttempt) + Math.random() * 400,
    )
    this.reconnectAttempt += 1
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      if (!this.intentionalClose) {
        this.openSocket('reconnecting')
      }
    }, delay)
  }
}

/** 模块级默认客户端（store 可再包一层） */
export const sharedWsClient = new WsClient()
