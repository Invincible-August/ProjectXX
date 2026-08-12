/**
 * 服务器相关 API 封装。
 * 后端需在 http 的 baseURL（如 /api/v1）下提供对应接口。
 */
import { http } from './http'
import type { ApiResponse } from '../types/api'
import type { ServerHealth } from '../types/server'

/**
 * 探测后端与数据库是否可用（GET /health，无需登录）。
 *
 * @returns 统一信封，data 含 status / app / env / db / time
 */
export async function fetchHealthApi(): Promise<ApiResponse<ServerHealth>> {
  const response = await http.get<ApiResponse<ServerHealth>>('/server/health')
  return response.data
}
