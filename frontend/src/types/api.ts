/**
 * 统一 API 响应信封（M0 §4.2）。
 */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T | null
}
