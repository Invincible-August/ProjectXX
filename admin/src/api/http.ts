/**
 * Axios：默认同源 ``/admin``（与后端同端口挂载时无需写死 8000）。
 * 可用 ``VITE_ADMIN_API_BASE_URL`` 覆盖（例如独立部署）。
 */
import axios from 'axios'
import type { ApiResponse } from '../types/api'

const adminBaseUrl =
  (import.meta.env.VITE_ADMIN_API_BASE_URL as string | undefined) || '/admin'

const TOKEN_KEY = 'px_admin_access_token'

export function getAdminToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setAdminToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

export const http = axios.create({
  baseURL: adminBaseUrl,
  timeout: 20_000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.request.use((config) => {
  const token = getAdminToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

/**
 * 解包统一信封；非 0 抛错。
 */
export async function unwrap<T>(promise: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  const { data } = await promise
  if (data.code !== 0) {
    throw new Error(data.message || `业务错误 ${data.code}`)
  }
  if (data.data === null || data.data === undefined) {
    throw new Error(data.message || '响应无 data')
  }
  return data.data
}
