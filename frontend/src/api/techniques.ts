/**
 * 功法 API（M2）。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type { TechniquesMeData } from '../types/techniques'

/**
 * 拉取我的功法列表。
 */
export async function fetchMyTechniquesApi(): Promise<ApiResponse<TechniquesMeData>> {
  try {
    const response = await http.get<ApiResponse<TechniquesMeData>>('/techniques/me')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TechniquesMeData>(error)
  }
}
