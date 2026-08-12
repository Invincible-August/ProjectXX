/**
 * 从 Axios 错误中提取统一信封；网络/CORS 等无响应时也返回可读信封（不抛）。
 * 业务错误（如 40005/40020）即使 HTTP 非 2xx，也尽量解析信封返回。
 */
import axios from 'axios'
import type { ApiResponse } from '../types/api'

/**
 * @param error - 捕获到的异常
 */
export function envelopeFromAxiosError<T>(error: unknown): ApiResponse<T> {
  if (axios.isAxiosError(error)) {
    if (error.response?.data) {
      const body = error.response.data as Partial<ApiResponse<T>>
      if (typeof body.code === 'number' && typeof body.message === 'string') {
        return {
          code: body.code,
          message: body.message,
          data: (body.data ?? null) as T,
        }
      }
      return {
        code: error.response.status || 50000,
        message: `请求失败（HTTP ${error.response.status}）`,
        data: null as T,
      }
    }
    // 无 response：断连 / CORS / 后端未启动 —— 浏览器常报 Network Error
    const hint =
      error.code === 'ERR_NETWORK'
        ? '无法连接后端（请确认 API 已启动，且 CORS 允许当前前端源；若刚死亡进引渡，多为服务端异常已修复后需刷新）'
        : error.message || '网络错误'
    return {
      code: 50001,
      message: hint,
      data: null as T,
    }
  }
  if (error instanceof Error) {
    return { code: 50001, message: error.message, data: null as T }
  }
  return { code: 50001, message: '未知网络错误', data: null as T }
}
