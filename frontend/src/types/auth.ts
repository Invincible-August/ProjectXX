/**
 * 鉴权相关 DTO：注册以邮箱/手机号标识；登录支持密码与短信验证码。
 */
export interface AuthUser {
  id: number
  email: string | null
  phone: string | null
  /** 展示名：优先邮箱，其次手机号 */
  display_name: string
}

export interface TokenPayload {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user?: AuthUser
  /** 是否已创角；登录 / refresh 与 /auth/me 同语义 */
  has_character: boolean
}

/** 登录方式：密码（邮箱或手机）/ 短信验证码 */
export type LoginMethod = 'password' | 'sms'

/** 密码登录请求 */
export interface PasswordLoginPayload {
  login_method: 'password'
  /** 邮箱或 11 位手机号 */
  account: string
  password: string
  remember_me: boolean
}

/** 短信验证码登录请求 */
export interface SmsLoginPayload {
  login_method: 'sms'
  phone: string
  sms_code: string
  remember_me: boolean
}

export type LoginPayload = PasswordLoginPayload | SmsLoginPayload

/** 注册请求体（与后端 RegisterRequest 对齐；可选字段由 REGISTER_REQUIRE_* 决定）。 */
export interface RegisterPayload {
  password: string
  email: string
  phone?: string
  real_name?: string
  id_card?: string
  sms_ticket?: string
  email_ticket?: string
  id_ticket?: string
}

export interface RegisterResult {
  user_id: number
  email: string | null
  phone: string | null
  display_name: string
  created_at: string
}

export interface AuthMeResult {
  id: number
  email: string | null
  phone: string | null
  display_name: string
  has_character: boolean
  created_at: string
}
