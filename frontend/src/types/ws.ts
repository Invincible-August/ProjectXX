/**
 * M6 WebSocket 信封与连接态类型（对齐设计 §4 / §7）。
 *
 * 聊天 / 传承命名空间仅预留，M6 不实现 UI。
 */

/** 连接生命周期 */
export type WsConnectionStatus =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'closed'

/** 通用 WS 信封 */
export type WsEnvelope<T = unknown> = {
  type: string
  seq: number
  ts: string
  payload: T
}

/** 客户端上行（可无 seq，由 client 填） */
export type WsClientMessage = {
  type: string
  seq?: number
  ts?: string
  payload?: Record<string, unknown>
}

/** sys.hello payload */
export interface WsHelloPayload {
  server_time?: string
  message?: string
  [key: string]: unknown
}

/** sys.error payload */
export interface WsErrorPayload {
  code?: number
  message: string
  [key: string]: unknown
}

/** room.state / dao_lord.room.state 快照 */
export interface WsRoomStatePayload {
  room_id: string
  kind?: string
  phase?: string
  members?: Array<{ character_id?: number; name?: string }>
  [key: string]: unknown
}

/** world.env 推送（与 WorldEnvPublic 宽松对齐） */
export interface WsWorldEnvPayload {
  shichen?: string
  shichen_label?: string
  weather?: string | Record<string, unknown>
  weather_label?: string
  next_shichen_at?: string
  hints?: Record<string, string>
  [key: string]: unknown
}

/** 事件监听器 */
export type WsEnvelopeHandler = (envelope: WsEnvelope) => void
