/**
 * 突破 API：预览 / 发起 / 真读条（M1 + M5-D05）。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  BreakthroughAttemptResult,
  BreakthroughChannelResponse,
  BreakthroughPreview,
  GradeHistoryItem,
} from '../types/breakthrough'

/** 生成幂等键 */
function newIdempotencyKey(prefix: string): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

/** GET /breakthrough/preview */
export async function previewBreakthroughApi(): Promise<
  ApiResponse<BreakthroughPreview>
> {
  try {
    const response = await http.get<ApiResponse<BreakthroughPreview>>(
      '/breakthrough/preview',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<BreakthroughPreview>(error)
  }
}

/** POST /breakthrough/attempt（兼容：真读条开启时=开读条） */
export async function attemptBreakthroughApi(): Promise<
  ApiResponse<BreakthroughAttemptResult>
> {
  try {
    const response = await http.post<ApiResponse<BreakthroughAttemptResult>>(
      '/breakthrough/attempt',
      { confirm: true },
      { headers: { 'Idempotency-Key': newIdempotencyKey('bt') } },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<BreakthroughAttemptResult>(error)
  }
}

/** POST /breakthrough/channel/start */
export async function startBreakthroughChannelApi(): Promise<
  ApiResponse<BreakthroughAttemptResult>
> {
  try {
    const response = await http.post<ApiResponse<BreakthroughAttemptResult>>(
      '/breakthrough/channel/start',
      { confirm: true },
      { headers: { 'Idempotency-Key': newIdempotencyKey('bt-ch') } },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<BreakthroughAttemptResult>(error)
  }
}

/** GET /breakthrough/channel */
export async function fetchBreakthroughChannelApi(): Promise<
  ApiResponse<BreakthroughChannelResponse>
> {
  try {
    const response = await http.get<ApiResponse<BreakthroughChannelResponse>>(
      '/breakthrough/channel',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<BreakthroughChannelResponse>(error)
  }
}

/** POST /breakthrough/channel/resolve */
export async function resolveBreakthroughChannelApi(): Promise<
  ApiResponse<BreakthroughAttemptResult>
> {
  try {
    const response = await http.post<ApiResponse<BreakthroughAttemptResult>>(
      '/breakthrough/channel/resolve',
      {},
      { headers: { 'Idempotency-Key': newIdempotencyKey('bt-rs') } },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<BreakthroughAttemptResult>(error)
  }
}

/** GET /breakthrough/grades/history */
export async function fetchGradeHistoryApi(): Promise<
  ApiResponse<{ items: GradeHistoryItem[] }>
> {
  try {
    const response = await http.get<ApiResponse<{ items: GradeHistoryItem[] }>>(
      '/breakthrough/grades/history',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{ items: GradeHistoryItem[] }>(error)
  }
}
