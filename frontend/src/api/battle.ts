/**
 * 战斗 API（M1 教学 PVE → M3 棋盘化 + PVP + 体力）。
 *
 * 战报零保留：无 reports 端点，开战响应即完整战报。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  AutochessBattleResult,
  MonsterInfo,
  OpponentInfo,
  StaminaState,
} from '../types/autochess'

/**
 * 发起棋盘化 PVE（M3 契约：响应即完整战报）。
 *
 * @param monsterId - 怪物键，默认 tutorial_slime
 * @param presetSlot - 进攻预设槽；缺省取 role=attack 预设
 */
function newIdempotencyKey(prefix: string): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export async function startPveApi(
  monsterId = 'tutorial_slime',
  presetSlot: number | null = null,
  useDao = false,
): Promise<ApiResponse<AutochessBattleResult>> {
  try {
    const response = await http.post<ApiResponse<AutochessBattleResult>>(
      '/battle/pve',
      {
        monster_id: monsterId,
        preset_slot: presetSlot,
        use_dao: useDao,
      },
      { headers: { 'Idempotency-Key': newIdempotencyKey('pve') } },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<AutochessBattleResult>(error)
  }
}

/**
 * 攻打目标玩家的防守快照（异步非对称 PVP）。
 *
 * @param targetCharacterId - 目标角色 id
 * @param presetSlot - 进攻预设槽
 */
export async function startPvpApi(
  targetCharacterId: number,
  presetSlot: number | null = null,
  useDao = false,
): Promise<ApiResponse<AutochessBattleResult>> {
  try {
    const response = await http.post<ApiResponse<AutochessBattleResult>>(
      '/battle/pvp/attack',
      {
        target_character_id: targetCharacterId,
        preset_slot: presetSlot,
        use_dao: useDao,
      },
      { headers: { 'Idempotency-Key': newIdempotencyKey('pvp') } },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<AutochessBattleResult>(error)
  }
}

/** 可挑战怪物列表（含体力消耗）。 */
export async function fetchMonstersApi(): Promise<
  ApiResponse<{ monsters: MonsterInfo[] }>
> {
  try {
    const response = await http.get<ApiResponse<{ monsters: MonsterInfo[] }>>(
      '/battle/pve/monsters',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{ monsters: MonsterInfo[] }>(error)
  }
}

/** 可攻打对手列表（M3 占位匹配）。 */
export async function fetchOpponentsApi(): Promise<
  ApiResponse<{ opponents: OpponentInfo[] }>
> {
  try {
    const response = await http.get<ApiResponse<{ opponents: OpponentInfo[] }>>(
      '/battle/pvp/opponents',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{ opponents: OpponentInfo[] }>(error)
  }
}

/** 当前体力读数（惰性恢复后）。 */
export async function fetchStaminaApi(): Promise<ApiResponse<StaminaState>> {
  try {
    const response = await http.get<ApiResponse<StaminaState>>('/battle/stamina')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<StaminaState>(error)
  }
}
