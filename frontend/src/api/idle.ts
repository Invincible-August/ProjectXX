/**
 * 挂机 API：方向 / sync / 离线领取（M1+M2）。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  IdleDirection,
  IdleSyncData,
  OfflineClaimData,
  OfflinePreviewData,
} from '../types/idle'

/**
 * 切换挂机方向。
 *
 * @param direction - none / spirit / body / crafting
 */
export async function setIdleDirectionApi(
  direction: IdleDirection,
): Promise<ApiResponse<IdleSyncData>> {
  try {
    const response = await http.post<ApiResponse<IdleSyncData>>('/idle/direction', {
      direction,
    })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<IdleSyncData>(error)
  }
}

/**
 * 权威入账同步（大厅按 next_tick_at 到点调用）。
 */
export async function syncIdleApi(): Promise<ApiResponse<IdleSyncData>> {
  try {
    const response = await http.post<ApiResponse<IdleSyncData>>('/idle/sync', {})
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<IdleSyncData>(error)
  }
}

/**
 * 离线收益预览（可能幂等生成 pending）。
 */
export async function previewOfflineApi(): Promise<ApiResponse<OfflinePreviewData>> {
  try {
    const response = await http.get<ApiResponse<OfflinePreviewData>>(
      '/idle/offline/preview',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<OfflinePreviewData>(error)
  }
}

/**
 * 领取离线 pending。
 */
export async function claimOfflineApi(): Promise<ApiResponse<OfflineClaimData>> {
  try {
    const response = await http.post<ApiResponse<OfflineClaimData>>(
      '/idle/offline/claim',
      {},
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<OfflineClaimData>(error)
  }
}
