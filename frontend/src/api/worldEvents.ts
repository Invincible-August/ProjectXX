/**
 * M6 世界事件骨架 HTTP API。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  WorldEventRegisterResult,
  WorldEventsCurrentPayload,
} from '../types/worldEvents'

/** GET /world-events/current */
export async function fetchCurrentEvents(): Promise<
  ApiResponse<WorldEventsCurrentPayload>
> {
  try {
    const response = await http.get<ApiResponse<WorldEventsCurrentPayload>>(
      '/world-events/current',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<WorldEventsCurrentPayload>(error)
  }
}

/**
 * POST /world-events/{id}/register — 报名占位。
 *
 * @param eventId - 事件 id
 */
export async function registerEvent(
  eventId: string | number,
): Promise<ApiResponse<WorldEventRegisterResult>> {
  try {
    const response = await http.post<ApiResponse<WorldEventRegisterResult>>(
      `/world-events/${eventId}/register`,
      {},
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<WorldEventRegisterResult>(error)
  }
}
