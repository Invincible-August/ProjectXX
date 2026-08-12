/**
 * 大厅游戏日志条目类型（M0 客户端本地事件流；后续可接服务端推送）。
 */
export type GameLogLevel = 'info' | 'success' | 'warning' | 'system'

export interface GameLogEntry {
  /** 稳定唯一键（用于 v-for） */
  id: string
  /** ISO 时间或本地可读时间 */
  time: string
  /** 日志正文 */
  message: string
  /** 展示级别 */
  level: GameLogLevel
}

/**
 * 生成一条日志条目。
 *
 * @param message - 正文
 * @param level - 级别，默认 info
 */
export function createLogEntry(
  message: string,
  level: GameLogLevel = 'info',
): GameLogEntry {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  const time = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
  return {
    id: `${now.getTime()}-${Math.random().toString(36).slice(2, 8)}`,
    time,
    message,
    level,
  }
}
