/**
 * M7 L7 双修 HTTP API。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  DualGender,
  DualMePayload,
  DualRanksPayload,
} from '../types/dualCultivation'

export async function fetchDualMe(): Promise<ApiResponse<DualMePayload>> {
  try {
    const response = await http.get<ApiResponse<DualMePayload>>('/dual/me')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<DualMePayload>(error)
  }
}

export async function setDualGender(
  gender: DualGender,
): Promise<ApiResponse<DualMePayload>> {
  try {
    const response = await http.post<ApiResponse<DualMePayload>>('/dual/set-gender', {
      gender,
    })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<DualMePayload>(error)
  }
}

export async function inviteDual(body: {
  technique_id: string
  target_name?: string
  target_character_id?: number
}): Promise<ApiResponse<{ session?: unknown; message?: string }>> {
  try {
    const response = await http.post('/dual/invite', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function confirmDual(
  sessionId: number,
): Promise<ApiResponse<{ session?: unknown; message?: string }>> {
  try {
    const response = await http.post(`/dual/${sessionId}/confirm`)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function rollDual(
  sessionId: number,
): Promise<ApiResponse<{ session?: unknown; dice?: unknown; message?: string }>> {
  try {
    const response = await http.post(`/dual/${sessionId}/roll`, {})
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function settleDual(
  sessionId: number,
): Promise<
  ApiResponse<{ session?: unknown; summary?: unknown; message?: string; character?: unknown }>
> {
  try {
    const response = await http.post(`/dual/${sessionId}/settle`)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function cancelDual(
  sessionId: number,
): Promise<ApiResponse<{ message?: string }>> {
  try {
    const response = await http.post(`/dual/${sessionId}/cancel`)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function fetchDualRanks(params?: {
  board?: string
  limit?: number
}): Promise<ApiResponse<DualRanksPayload>> {
  try {
    const response = await http.get<ApiResponse<DualRanksPayload>>('/dual/ranks', {
      params,
    })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<DualRanksPayload>(error)
  }
}
