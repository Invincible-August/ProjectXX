/**
 * 神通 API。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  DivineAbilitiesMeData,
  DivineAbilityEquipRequest,
  DivineAbilityUnequipRequest,
} from '../types/divineAbilities'

export async function fetchMyDivineAbilitiesApi(
  actor: 'main' | 'avatar' = 'main',
): Promise<ApiResponse<DivineAbilitiesMeData>> {
  try {
    const response = await http.get<ApiResponse<DivineAbilitiesMeData>>(
      '/divine-abilities/me',
      { params: { actor } },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<DivineAbilitiesMeData>(error)
  }
}

export async function equipDivineAbilityApi(
  body: DivineAbilityEquipRequest,
): Promise<ApiResponse<DivineAbilitiesMeData>> {
  try {
    const response = await http.post<ApiResponse<DivineAbilitiesMeData>>(
      '/divine-abilities/equip',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<DivineAbilitiesMeData>(error)
  }
}

export async function unequipDivineAbilityApi(
  body: DivineAbilityUnequipRequest,
): Promise<ApiResponse<DivineAbilitiesMeData>> {
  try {
    const response = await http.post<ApiResponse<DivineAbilitiesMeData>>(
      '/divine-abilities/unequip',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<DivineAbilitiesMeData>(error)
  }
}
