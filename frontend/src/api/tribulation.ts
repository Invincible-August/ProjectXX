/**
 * M5 渡劫 API：准备 / 遮天 / 开渡 / 批次结算。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  TribulationMutationResult,
  TribulationPrepPayload,
  TribulationSessionPublic,
  TribulationVeilResult,
} from '../types/tribulation'

/** GET /tribulation/me */
export async function fetchTribulation(): Promise<
  ApiResponse<{ session: TribulationSessionPublic | null }>
> {
  try {
    const response = await http.get<
      ApiResponse<{ session: TribulationSessionPublic | null }>
    >('/tribulation/me')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{ session: TribulationSessionPublic | null }>(error)
  }
}

/** POST /tribulation/start-prep */
export async function startPrep(): Promise<ApiResponse<TribulationMutationResult>> {
  try {
    const response = await http.post<ApiResponse<TribulationMutationResult>>(
      '/tribulation/start-prep',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TribulationMutationResult>(error)
  }
}

/** PUT /tribulation/prep */
export async function savePrep(
  payload: TribulationPrepPayload,
): Promise<ApiResponse<TribulationMutationResult>> {
  try {
    const response = await http.put<ApiResponse<TribulationMutationResult>>(
      '/tribulation/prep',
      payload,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TribulationMutationResult>(error)
  }
}

/** POST /tribulation/commit-prep */
export async function commitPrep(): Promise<ApiResponse<TribulationMutationResult>> {
  try {
    const response = await http.post<ApiResponse<TribulationMutationResult>>(
      '/tribulation/commit-prep',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TribulationMutationResult>(error)
  }
}

/** POST /tribulation/veil-check */
export async function veilCheck(): Promise<ApiResponse<TribulationVeilResult>> {
  try {
    const response = await http.post<ApiResponse<TribulationVeilResult>>(
      '/tribulation/veil-check',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TribulationVeilResult>(error)
  }
}

/** POST /tribulation/begin */
export async function beginTribulation(): Promise<
  ApiResponse<TribulationMutationResult>
> {
  try {
    const response = await http.post<ApiResponse<TribulationMutationResult>>(
      '/tribulation/begin',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TribulationMutationResult>(error)
  }
}

/** POST /tribulation/resolve-batch */
export async function resolveBatch(body?: {
  batch_size?: number
}): Promise<ApiResponse<TribulationMutationResult>> {
  try {
    const response = await http.post<ApiResponse<TribulationMutationResult>>(
      '/tribulation/resolve-batch',
      body ?? {},
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TribulationMutationResult>(error)
  }
}

/** POST /tribulation/auto-resolve */
export async function autoResolve(): Promise<ApiResponse<TribulationMutationResult>> {
  try {
    const response = await http.post<ApiResponse<TribulationMutationResult>>(
      '/tribulation/auto-resolve',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TribulationMutationResult>(error)
  }
}
