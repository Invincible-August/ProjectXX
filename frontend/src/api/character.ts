/**
 * 角色 API：创建角色、获取我的角色（对齐 M0 §5.6 / §5.7）。
 * 业务错误（如 40005）即使 HTTP 非 2xx，也尽量解析统一信封返回，便于 store 分支处理。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  CharacterPublic,
  CreateCharacterPayload,
} from '../types/character'

/**
 * 创建角色（需 Bearer；一账号一角色）。
 *
 * @param payload - 仅含角色名
 */
export async function createCharacterApi(
  payload: CreateCharacterPayload,
): Promise<ApiResponse<CharacterPublic>> {
  try {
    const response = await http.post<ApiResponse<CharacterPublic>>(
      '/characters',
      payload,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<CharacterPublic>(error)
  }
}

/**
 * 获取当前账号的角色面板数据（服务端会先 settle）。
 */
export async function fetchMyCharacterApi(): Promise<
  ApiResponse<CharacterPublic>
> {
  try {
    const response = await http.get<ApiResponse<CharacterPublic>>(
      '/characters/me',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<CharacterPublic>(error)
  }
}

/**
 * 获取统一战斗/生活属性块（与面板同源 build_combat_attrs）。
 */
export async function fetchMyCombatAttrsApi(): Promise<
  ApiResponse<{ combat: CharacterPublic['combat']; life: CharacterPublic['life'] }>
> {
  try {
    const response = await http.get<
      ApiResponse<{ combat: CharacterPublic['combat']; life: CharacterPublic['life'] }>
    >('/characters/me/combat')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/**
 * 确认待领取事件日志已展示（无离线 pending 时服务端清空）。
 */
export async function ackPendingEventLogsApi(): Promise<
  ApiResponse<{
    cleared: number
    skipped: boolean
    character: CharacterPublic
  }>
> {
  try {
    const response = await http.post<
      ApiResponse<{
        cleared: number
        skipped: boolean
        character: CharacterPublic
      }>
    >('/characters/me/event-logs/ack')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}
