/**
 * M5 / M7 L6 待引渡 API：自救 / 社交引渡 / 自选进入轮回。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  FerryMutationResult,
  FerryPublic,
  FerryRescueRequest,
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
 * POST /ferry/rescue — 道友/同门引渡（救援者支付）。
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
