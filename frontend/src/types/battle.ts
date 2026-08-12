/**
 * 战斗 API 类型。
 *
 * M3 起 `/battle/pve` 返回棋盘化战报（见 types/autochess.ts）；
 * 本文件中的 M1 rounds 类型已废弃，仅为兼容保留。
 */
import type { CharacterPublic } from './character'

export type { AutochessBattleResult } from './autochess'

/**
 * 单回合战报（M1）。
 *
 * @deprecated M3 战报改为 events[]（types/autochess.ts）；UI 不应再渲染此结构。
 */
export interface BattleRound {
  round: number
  actor: 'player' | 'monster' | string
  action: string
  damage: number
  attacker_hp_after: number
  defender_hp_after: number
  text: string
}

/**
 * POST /battle/pve 旧响应（M1）。
 *
 * @deprecated M3 起响应为 AutochessBattleResult。
 */
export interface PveBattleResult {
  result: 'win' | 'lose'
  monster_id: string
  monster_name: string
  rounds: BattleRound[]
  rewards: {
    cultivation_points: number
    spirit_stones: number
  }
  character: CharacterPublic
}
