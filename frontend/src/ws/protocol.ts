/**
 * M6/M7 WS 协议常量与类型守卫。
 *
 * 命名空间：sys.* / world.* / dao_lord.* / event.* / chat.* / heritage.*。
 */
import type { WsEnvelope } from '../types/ws'

/** 已知 type 字符串（最低集） */
export const WsType = {
  SYS_HELLO: 'sys.hello',
  SYS_ERROR: 'sys.error',
  PING: 'ping',
  PONG: 'pong',
  ROOM_JOIN: 'room.join',
  ROOM_LEAVE: 'room.leave',
  ROOM_STATE: 'room.state',
  WORLD_ENV: 'world.env',
  AUTH: 'auth',
  DAO_LORD_ROOM_STATE: 'dao_lord.room.state',
  DAO_LORD_BATTLE_EVENT: 'dao_lord.battle.event',
  DAO_LORD_CONTEST_STATE: 'dao_lord.contest.state',
  DAO_LORD_MATCH_FINISHED: 'dao_lord.match.finished',
  DAO_LORD_LIVE_TICK: 'dao_lord.live.tick',
  EVENT_UPDATE: 'event.update',
  CHAT_MESSAGE: 'chat.message',
  CHAT_UNREAD: 'chat.unread',
  CHAT_RECALL: 'chat.recall',
  CHAT_DM_CLEARED: 'chat.dm.cleared',
  PARTY_INVITE: 'party.invite',
  PARTY_UPDATE: 'party.update',
  PRESENCE_CHANGED: 'presence.changed',
  HERITAGE_CREATED: 'heritage.created',
  HERITAGE_CLAIMED: 'heritage.claimed',
  HERITAGE_EXPIRED: 'heritage.expired',
} as const

export type WsTypeValue = (typeof WsType)[keyof typeof WsType]

/**
 * 判断未知 JSON 是否为合法信封外壳。
 *
 * @param raw - 解析后的对象
 */
export function isWsEnvelope(raw: unknown): raw is WsEnvelope {
  if (!raw || typeof raw !== 'object') return false
  const o = raw as Record<string, unknown>
  return (
    typeof o.type === 'string' &&
    typeof o.seq === 'number' &&
    typeof o.ts === 'string' &&
    'payload' in o
  )
}

/**
 * 宽松解析：缺 seq/ts 时补默认，便于兼容 DEV 桩。
 *
 * @param raw - 原始对象
 */
export function coerceWsEnvelope(raw: unknown): WsEnvelope | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  if (typeof o.type !== 'string') return null
  return {
    type: o.type,
    seq: typeof o.seq === 'number' ? o.seq : 0,
    ts: typeof o.ts === 'string' ? o.ts : new Date().toISOString(),
    payload: o.payload ?? {},
  }
}

/**
 * 是否为道主房间相关推送。
 *
 * @param type - envelope.type
 */
export function isDaoLordRoomType(type: string): boolean {
  return (
    type === WsType.ROOM_STATE ||
    type === WsType.DAO_LORD_ROOM_STATE ||
    type.startsWith('dao_lord.')
  )
}
