/**
 * M5 / M7 L6 待引渡 API：自救 / 社交引渡 / 自选进入轮回。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  FerryMutationResult,
  FerryPublic,
  FerryRescueCategory,
  FerryRescueRequest,
  FerryRescueTargetsPayload,
} from '../types/ferry'

/** GET /ferry/me */
export async function fetchFerry(): Promise<ApiResponse<FerryPublic | null>> {
  try {
    const response = await http.get<ApiResponse<FerryPublic | null>>('/ferry/me')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FerryPublic | null>(error)
  }
}

/**
 * GET /ferry/rescue-targets — 按类别列出待引渡目标。
 *
 * @param category - universal | sect | kin
 */
export async function fetchRescueTargets(
  category: FerryRescueCategory = 'universal',
): Promise<ApiResponse<FerryRescueTargetsPayload>> {
  try {
    const response = await http.get<ApiResponse<FerryRescueTargetsPayload>>(
      '/ferry/rescue-targets',
      { params: { category } },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /ferry/self-rescue */
export async function selfRescue(): Promise<ApiResponse<FerryMutationResult>> {
  try {
    const response = await http.post<ApiResponse<FerryMutationResult>>(
      '/ferry/self-rescue',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FerryMutationResult>(error)
  }
}

/**
 * POST /ferry/rescue — 普渡/同门/亲友引渡（救援者支付）。
 *
 * @param body - mode + 目标道号或角色 id
 */
export async function socialRescue(
  body: FerryRescueRequest,
): Promise<ApiResponse<FerryMutationResult>> {
  try {
    const response = await http.post<ApiResponse<FerryMutationResult>>(
      '/ferry/rescue',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FerryMutationResult>(error)
  }
}

/** POST /ferry/enter-reincarnation */
export async function enterReincarnation(body?: {
  confirm?: boolean
}): Promise<ApiResponse<FerryMutationResult>> {
  try {
    const response = await http.post<ApiResponse<FerryMutationResult>>(
      '/ferry/enter-reincarnation',
      { confirm: true, ...body },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<FerryMutationResult>(error)
  }
}
