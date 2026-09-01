/**
 * 页面侧写游戏日志的薄封装（统一落到 gameLogStore，按角色持久化）。
 */
import { useGameLogStore } from '../stores/gameLog'
import type { GameLogEntry, GameLogLevel } from '../types/gameLog'

/**
 * @returns pushLog - 与各页原有 ``@log="pushLog"`` 签名兼容
 */
export function useGameLogPush(): {
  gameLogStore: ReturnType<typeof useGameLogStore>
  pushLog: (message: string, level?: GameLogEntry['level']) => void
} {
  const gameLogStore = useGameLogStore()

  function pushLog(message: string, level: GameLogLevel = 'info'): void {
    gameLogStore.push(message, level)
  }

  return { gameLogStore, pushLog }
}
