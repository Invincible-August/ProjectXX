/**
 * 道侣 / 炉鼎 HTTP API。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type { BondListPayload } from '../types/bonds'

export async function listBonds(): Promise<ApiResponse<BondListPayload>> {
  try {
    const response = await http.get<ApiResponse<BondListPayload>>('/bonds')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<BondListPayload>(error)
  }
}

export async function applyCompanion(body: {
  target_name?: string | null
  target_character_id?: number | null
}): Promise<ApiResponse<{ message?: string; bond_id?: number }>> {
  try {
    const response = await http.post('/bonds/companions', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function applyVessel(body: {
  target_name?: string | null
  target_character_id?: number | null
}): Promise<ApiResponse<{ message?: string }>> {
  try {
    const response = await http.post('/bonds/vessels', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function acceptBond(
  bondId: number,
): Promise<ApiResponse<{ message?: string; bond_id?: number }>> {
  try {
    const response = await http.post(`/bonds/${bondId}/accept`)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function rejectBond(
  bondId: number,
): Promise<ApiResponse<{ message?: string; bond_id?: number }>> {
  try {
    const response = await http.post(`/bonds/${bondId}/reject`)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function removeBond(
  bondId: number,
): Promise<ApiResponse<{ message?: string; bond_id?: number }>> {
  try {
    const response = await http.delete(`/bonds/${bondId}`)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}
