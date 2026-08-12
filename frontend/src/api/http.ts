/**
 * Axios 实例：自动附加 Bearer；收到 HTTP 401 时尝试 refresh 一次后重试。
 */
import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import {
  getAccessToken,
  getRefreshToken,
  getRememberMe,
  persistTokens,
  clearTokens,
} from '../utils/storage'
import type { ApiResponse } from '../types/api'
import type { TokenPayload } from '../types/auth'

const apiBaseUrl =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ||
  'http://127.0.0.1:8000/api/v1'

export const http = axios.create({
  baseURL: apiBaseUrl,
  timeout: 15_000,
  headers: {
    'Content-Type': 'application/json',
  },
})

/** 标记：该请求已经做过一次 refresh 重试，防止死循环 */
type RetryConfig = InternalAxiosRequestConfig & { _retried?: boolean }

http.interceptors.request.use((config) => {
  const accessToken = getAccessToken()
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`
  }
  return config
})

/**
 * 单独用原生 axios 调 refresh，避免走本实例拦截器造成递归。
 */
async function requestTokenRefresh(): Promise<boolean> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return false
  try {
    const response = await axios.post<ApiResponse<TokenPayload>>(
      `${apiBaseUrl}/auth/refresh`,
      { refresh_token: refreshToken },
      { timeout: 15_000 },
    )
    const envelope = response.data
    if (envelope.code !== 0 || !envelope.data) {
      clearTokens()
      // 同步清空 Pinia，避免 hasCharacter=false 残留
      void import('../stores/auth').then(({ useAuthStore }) => {
        useAuthStore().logout()
      })
      return false
    }
    persistTokens(
      envelope.data.access_token,
      envelope.data.refresh_token,
      getRememberMe(),
    )
    // 同步 Pinia（含 has_character）
    void import('../stores/auth').then(({ useAuthStore }) => {
      useAuthStore().applyTokenPayload(envelope.data!, getRememberMe())
    })
    return true
  } catch {
    clearTokens()
    void import('../stores/auth').then(({ useAuthStore }) => {
      useAuthStore().logout()
    })
    return false
  }
}

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetryConfig | undefined
    const status = error.response?.status
    // 仅对受保护接口的 401 尝试刷新；登录/注册本身的 401 不处理
    const url = original?.url ?? ''
    const isAuthPublic =
      url.includes('/auth/login') ||
      url.includes('/auth/register') ||
      url.includes('/auth/refresh')

    if (status === 401 && original && !original._retried && !isAuthPublic) {
      original._retried = true
      const refreshed = await requestTokenRefresh()
      if (refreshed) {
        const nextToken = getAccessToken()
        if (nextToken) {
          original.headers.Authorization = `Bearer ${nextToken}`
        }
        return http.request(original)
      }
    }
    return Promise.reject(error)
  },
)
