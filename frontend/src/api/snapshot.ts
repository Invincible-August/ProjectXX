/**
 * 防守快照 API（M3）：我的摘要 / 手动更新 / 攻打前预览。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  MySnapshotPayload,
  SnapshotPreviewPayload,
} from '../types/formation'

/** 我的快照摘要（读取路径会触发服务端惰性每日补刷）。 */
export async function fetchMySnapshotApi(): Promise<ApiResponse<MySnapshotPayload>> {
  try {
    const response = await http.get<ApiResponse<MySnapshotPayload>>('/snapshot/defense/me')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<MySnapshotPayload>(error)
  }
}

/** 手动更新防守快照（冷却中 → 40045；状态禁止 → 40046）。 */
export async function updateDefenseSnapshotApi(): Promise<
  ApiResponse<{ snapshot: MySnapshotPayload['snapshot']; cooldown_remaining_seconds: number }>
> {
  try {
    const response = await http.post<
      ApiResponse<{ snapshot: MySnapshotPayload['snapshot']; cooldown_remaining_seconds: number }>
    >('/snapshot/defense/update')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/**
 * 攻打前预览目标快照（无快照 → 40048）。
 *
 * @param characterId - 目标角色 id
 */
export async function previewSnapshotApi(
  characterId: number,
): Promise<ApiResponse<SnapshotPreviewPayload>> {
  try {
    const response = await http.get<ApiResponse<SnapshotPreviewPayload>>(
      `/snapshot/defense/${characterId}`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<SnapshotPreviewPayload>(error)
  }
}
