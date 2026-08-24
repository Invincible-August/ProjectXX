/**
 * 功法 API。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  TechniqueEquipRequest,
  TechniqueUnequipRequest,
  TechniquesMeData,
} from '../types/techniques'

export async function fetchMyTechniquesApi(
  actor: 'main' | 'avatar' = 'main',
): Promise<ApiResponse<TechniquesMeData>> {
  try {
    const response = await http.get<ApiResponse<TechniquesMeData>>('/techniques/me', {
      params: { actor },
    })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TechniquesMeData>(error)
  }
}

export async function equipTechniqueApi(
  body: TechniqueEquipRequest,
): Promise<ApiResponse<TechniquesMeData>> {
  try {
    const response = await http.post<ApiResponse<TechniquesMeData>>(
      '/techniques/equip',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TechniquesMeData>(error)
  }
}

export async function unequipTechniqueApi(
  body: TechniqueUnequipRequest,
): Promise<ApiResponse<TechniquesMeData>> {
  try {
    const response = await http.post<ApiResponse<TechniquesMeData>>(
      '/techniques/unequip',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TechniquesMeData>(error)
  }
}
