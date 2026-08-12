/**
 * 鉴权相关 API 封装（登录 / 注册 / refresh / me）。
 * 注册携带邮箱、手机、实名、证件及三张核验 ticket（无用户名）。
 */
import { http } from './http'
import type { ApiResponse } from '../types/api'
import type {
  AuthMeResult,
  LoginPayload,
  RegisterPayload,
  RegisterResult,
  TokenPayload,
} from '../types/auth'

/**
 * 注册新账号（按约定：注册成功不自动登录）。
 *
 * @param payload - 密码 + 核验材料与三张 ticket（邮箱/手机必填）
 */
export async function registerApi(
  payload: RegisterPayload,
): Promise<ApiResponse<RegisterResult>> {
  const response = await http.post<ApiResponse<RegisterResult>>(
    '/auth/register',
    payload,
  )
  return response.data
}

/**
 * 登录并获取 JWT（access + refresh）。
 *
 * 支持：邮箱/手机 + 密码、手机 + 短信验证码。
 *
 * @param payload - 登录方式与对应凭证
 */
export async function loginApi(
  payload: LoginPayload,
): Promise<ApiResponse<TokenPayload>> {
  const response = await http.post<ApiResponse<TokenPayload>>(
    '/auth/login',
    payload,
  )
  return response.data
}

/**
 * 使用 refresh_token 换取新的双令牌。
 *
 * @param refreshToken - 本地持久化的 refresh JWT
 */
export async function refreshApi(
  refreshToken: string,
): Promise<ApiResponse<TokenPayload>> {
  const response = await http.post<ApiResponse<TokenPayload>>('/auth/refresh', {
    refresh_token: refreshToken,
  })
  return response.data
}

/**
 * 获取当前登录用户资料（请求头需带 Bearer access_token）。
 */
export async function fetchMeApi(): Promise<ApiResponse<AuthMeResult>> {
  const response = await http.get<ApiResponse<AuthMeResult>>('/auth/me')
  return response.data
}
