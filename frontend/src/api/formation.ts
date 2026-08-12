/**
 * 布阵 API（M3）：棋盘元数据 / 预设 CRUD / 干跑校验。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  BoardMeta,
  FormationPreset,
  PresetsPayload,
  UnitPlacement,
} from '../types/formation'

/** 拉取棋盘只读元数据（画盘 / 高亮用）。 */
export async function fetchBoardMetaApi(): Promise<ApiResponse<BoardMeta>> {
  try {
    const response = await http.get<ApiResponse<BoardMeta>>('/formation/board-meta')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<BoardMeta>(error)
  }
}

/** 拉取预设三槽 + 阵法 + Bench + 上阵上限。 */
export async function fetchPresetsApi(): Promise<ApiResponse<PresetsPayload>> {
  try {
    const response = await http.get<ApiResponse<PresetsPayload>>('/formation/presets')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<PresetsPayload>(error)
  }
}

/**
 * 保存一个预设槽。
 *
 * @param slot - 槽位（0/1/2）
 * @param body - 名称 / 定位 / 阵法 / 占位
 */
export async function savePresetApi(
  slot: number,
  body: {
    name: string
    role: string
    formation_id: string
    units: UnitPlacement[]
  },
): Promise<ApiResponse<FormationPreset>> {
  try {
    const response = await http.put<ApiResponse<FormationPreset>>(
      `/formation/presets/${slot}`,
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FormationPreset>(error)
  }
}

/** GET /formation/bench — 可上阵棋子源（M4）。 */
export async function fetchBenchApi(): Promise<
  ApiResponse<{ bench: import('../types/formation').BenchUnit[] }>
> {
  try {
    const response = await http.get<
      ApiResponse<{ bench: import('../types/formation').BenchUnit[] }>
    >('/formation/bench')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{ bench: import('../types/formation').BenchUnit[] }>(
      error,
    )
  }
}

/** 干跑校验占位（编辑器实时反馈；不落库）。 */
export async function validateFormationApi(body: {
  formation_id: string
  units: UnitPlacement[]
}): Promise<ApiResponse<{ valid: boolean }>> {
  try {
    const response = await http.post<ApiResponse<{ valid: boolean }>>(
      '/formation/validate',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{ valid: boolean }>(error)
  }
}
