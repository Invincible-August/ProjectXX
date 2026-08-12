/**
 * 资源分配 API（M2）。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type { AllocateRequest, AllocateResult } from '../types/allocate'

/**
 * 将池资源投入境界进度或功法。
 *
 * @param payload - 分配请求
 */
export async function allocateApi(
  payload: AllocateRequest,
): Promise<ApiResponse<AllocateResult>> {
  try {
    const response = await http.post<ApiResponse<AllocateResult>>(
      '/allocate',
      payload,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<AllocateResult>(error)
  }
}
