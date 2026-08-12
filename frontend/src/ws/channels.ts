/**
 * 聊天频道 WS 订阅辅助（M7 L4）。
 */
import { joinRoom, leaveRoom, type WsSender } from './rooms'

/**
 * 订阅聊天房 ``chat:{channel_ref}``。
 *
 * @param client - WS 发送面
 * @param roomId - 完整 room_id（服务端下发）
 */
export function subscribeChannel(client: WsSender, roomId: string): boolean {
  const id = roomId.trim()
  if (!id) return false
  return joinRoom(client, id, { kind: 'chat' })
}

/**
 * 取消订阅聊天房。
 */
export function unsubscribeChannel(client: WsSender, roomId: string): boolean {
  const id = roomId.trim()
  if (!id) return false
  return leaveRoom(client, id)
}
