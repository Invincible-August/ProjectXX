/**
 * M6 WS 房间 join / leave 辅助。
 */
import type { WsClientMessage } from '../types/ws'
import { WsType } from './protocol'

/** 仅需 send 的最小客户端表面（兼容 Pinia 暴露的实例） */
export type WsSender = {
  send: (message: WsClientMessage) => boolean
}

/**
 * 加入房间。
 *
 * @param client - WS 客户端
 * @param roomId - 房间 id
 * @param extra - 附加字段（如 challenge_id）
 */
export function joinRoom(
  client: WsSender,
  roomId: string,
  extra?: Record<string, unknown>,
): boolean {
  return client.send({
    type: WsType.ROOM_JOIN,
    payload: { room_id: roomId, ...extra },
  })
}

/**
 * 离开房间。
 *
 * @param client - WS 客户端
 * @param roomId - 房间 id
 */
export function leaveRoom(client: WsSender, roomId: string): boolean {
  return client.send({
    type: WsType.ROOM_LEAVE,
    payload: { room_id: roomId },
  })
}
