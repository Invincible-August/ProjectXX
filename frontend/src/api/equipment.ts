/**
 * Equipment API (M8 R0 · 17-zone + puppet loadout).
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  EquipmentEquipRequest,
  EquipmentEquipResponse,
  EquipmentState,
  EquipmentUnequipRequest,
  PuppetLoadoutReplaceRequest,
  PuppetLoadoutRequest,
  AvatarDeployRequest,
  TalismanLoadoutReplaceRequest,
} from '../types/equipment'

export async function fetchEquipmentSlotsApi(
  actor: 'main' | 'avatar' = 'main',
): Promise<ApiResponse<EquipmentEquipResponse>> {
  try {
    const response = await http.get<ApiResponse<EquipmentEquipResponse>>('/equipment/slots', {
      params: { actor },
    })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<EquipmentEquipResponse>(error)
  }
}

export async function equipItemApi(
  payload: EquipmentEquipRequest,
): Promise<ApiResponse<EquipmentEquipResponse>> {
  try {
    const response = await http.post<ApiResponse<EquipmentEquipResponse>>(
      '/equipment/equip',
      payload,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<EquipmentEquipResponse>(error)
  }
}

export async function unequipSlotApi(
  payload: EquipmentUnequipRequest,
): Promise<ApiResponse<EquipmentEquipResponse>> {
  try {
    const response = await http.post<ApiResponse<EquipmentEquipResponse>>(
      '/equipment/unequip',
      payload,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<EquipmentEquipResponse>(error)
  }
}

export async function addPuppetLoadoutApi(
  payload: PuppetLoadoutRequest,
): Promise<ApiResponse<EquipmentEquipResponse>> {
  try {
    const response = await http.post<ApiResponse<EquipmentEquipResponse>>(
      '/equipment/puppet-loadout/add',
      payload,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<EquipmentEquipResponse>(error)
  }
}

export async function removePuppetLoadoutApi(
  payload: PuppetLoadoutRequest,
): Promise<ApiResponse<EquipmentEquipResponse>> {
  try {
    const response = await http.post<ApiResponse<EquipmentEquipResponse>>(
      '/equipment/puppet-loadout/remove',
      payload,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<EquipmentEquipResponse>(error)
  }
}

export async function replacePuppetLoadoutApi(
  payload: PuppetLoadoutReplaceRequest,
): Promise<ApiResponse<EquipmentEquipResponse>> {
  try {
    const response = await http.put<ApiResponse<EquipmentEquipResponse>>(
      '/equipment/puppet-loadout',
      payload,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<EquipmentEquipResponse>(error)
  }
}

export async function setAvatarDeployApi(
  payload: AvatarDeployRequest,
): Promise<ApiResponse<EquipmentEquipResponse>> {
  try {
    const response = await http.post<ApiResponse<EquipmentEquipResponse>>(
      '/equipment/avatar-deploy',
      payload,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<EquipmentEquipResponse>(error)
  }
}

export async function replaceTalismanLoadoutApi(
  payload: TalismanLoadoutReplaceRequest,
): Promise<ApiResponse<EquipmentEquipResponse>> {
  try {
    const response = await http.put<ApiResponse<EquipmentEquipResponse>>(
      '/equipment/talisman-loadout',
      payload,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<EquipmentEquipResponse>(error)
  }
}

export async function fetchEquipmentCatalogApi(): Promise<
  ApiResponse<{ items: Array<Record<string, unknown>> }>
> {
  try {
    const response = await http.get<ApiResponse<{ items: Array<Record<string, unknown>> }>>(
      '/equipment/catalog',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{ items: Array<Record<string, unknown>> }>(error)
  }
}

export type { EquipmentState }
