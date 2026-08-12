/**
 * 体质 API（M2 骨架）。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  ConstitutionEquipRequest,
  ConstitutionState,
  ConstitutionUnequipRequest,
} from '../types/constitution'

/**
 * 拉取体质背包与格子。
 */
export async function fetchConstitutionApi(): Promise<ApiResponse<ConstitutionState>> {
  try {
    const response = await http.get<ApiResponse<ConstitutionState>>('/constitution/me')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<ConstitutionState>(error)
  }
}

/**
 * 镶嵌。
 *
 * @param payload - 物品与目标格
 */
export async function equipConstitutionApi(
  payload: ConstitutionEquipRequest,
): Promise<ApiResponse<{ constitution: ConstitutionState }>> {
  try {
    const response = await http.post<ApiResponse<{ constitution: ConstitutionState }>>(
      '/constitution/equip',
      payload,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{ constitution: ConstitutionState }>(error)
  }
}

/**
 * 卸下。
 *
 * @param payload - 目标格
 */
export async function unequipConstitutionApi(
  payload: ConstitutionUnequipRequest,
): Promise<ApiResponse<{ constitution: ConstitutionState }>> {
  try {
    const response = await http.post<ApiResponse<{ constitution: ConstitutionState }>>(
      '/constitution/unequip',
      payload,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{ constitution: ConstitutionState }>(error)
  }
}

/**
 * 升品占位。
 *
 * @param itemId - 背包物品 id
 */
export async function upgradeConstitutionApi(
  itemId: number,
): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/constitution/upgrade',
      { item_id: itemId },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<Record<string, unknown>>(error)
  }
}

/**
 * 融合占位。
 *
 * @param itemIds - 材料物品 id 列表
 */
export async function fuseConstitutionApi(
  itemIds: number[],
): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/constitution/fuse',
      { item_ids: itemIds },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<Record<string, unknown>>(error)
  }
}
