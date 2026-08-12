/**
 * JWT 持久化工具：配合「记住登录」在 localStorage / sessionStorage 之间切换。
 *
 * - remember_me=true → localStorage（关闭浏览器后仍可恢复登录）
 * - remember_me=false → sessionStorage（仅当前标签页会话）
 */

const ACCESS_TOKEN_KEY = 'xiuxian_access_token'
const REFRESH_TOKEN_KEY = 'xiuxian_refresh_token'
const REMEMBER_FLAG_KEY = 'xiuxian_remember_me'

/**
 * 根据是否记住登录，选择读写用的 Storage。
 *
 * @param rememberMe - true 用 localStorage；false 用 sessionStorage
 */
function resolveStore(rememberMe: boolean): Storage {
  return rememberMe ? localStorage : sessionStorage
}

/**
 * 读取当前应使用的 Storage（优先看记住标记；若无标记则探测两处是否已有 token）。
 */
function currentStore(): Storage {
  const flag = localStorage.getItem(REMEMBER_FLAG_KEY)
  if (flag === '0') return sessionStorage
  if (flag === '1') return localStorage
  // 兼容旧数据：哪边有 refresh 就用哪边
  if (sessionStorage.getItem(REFRESH_TOKEN_KEY)) return sessionStorage
  return localStorage
}

/**
 * 记录「记住登录」偏好，并清理另一侧 Storage 中的残留令牌，避免双份状态。
 *
 * @param rememberMe - 是否跨会话保存登录
 */
export function setRememberMe(rememberMe: boolean): void {
  localStorage.setItem(REMEMBER_FLAG_KEY, rememberMe ? '1' : '0')
  const other = rememberMe ? sessionStorage : localStorage
  other.removeItem(ACCESS_TOKEN_KEY)
  other.removeItem(REFRESH_TOKEN_KEY)
}

/**
 * 当前是否为「记住登录」模式。
 */
export function getRememberMe(): boolean {
  return localStorage.getItem(REMEMBER_FLAG_KEY) !== '0'
}

/**
 * 保存或清除 access_token。
 *
 * @param token - JWT 字符串；传 null 表示删除
 */
export function setAccessToken(token: string | null): void {
  const store = currentStore()
  if (token === null) {
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    sessionStorage.removeItem(ACCESS_TOKEN_KEY)
    return
  }
  store.setItem(ACCESS_TOKEN_KEY, token)
}

/**
 * 读取 access_token。
 *
 * @returns 已存储的令牌，没有则为 null
 */
export function getAccessToken(): string | null {
  return (
    localStorage.getItem(ACCESS_TOKEN_KEY) ||
    sessionStorage.getItem(ACCESS_TOKEN_KEY)
  )
}

/**
 * 保存或清除 refresh_token。
 *
 * @param token - JWT 字符串；传 null 表示删除
 */
export function setRefreshToken(token: string | null): void {
  const store = currentStore()
  if (token === null) {
    localStorage.removeItem(REFRESH_TOKEN_KEY)
    sessionStorage.removeItem(REFRESH_TOKEN_KEY)
    return
  }
  store.setItem(REFRESH_TOKEN_KEY, token)
}

/**
 * 读取 refresh_token。
 *
 * @returns 已存储的令牌，没有则为 null
 */
export function getRefreshToken(): string | null {
  return (
    localStorage.getItem(REFRESH_TOKEN_KEY) ||
    sessionStorage.getItem(REFRESH_TOKEN_KEY)
  )
}

/**
 * 一次写入双令牌，并按 rememberMe 选择持久化介质。
 *
 * @param accessToken - access JWT
 * @param refreshToken - refresh JWT
 * @param rememberMe - 是否跨浏览器会话保存
 */
export function persistTokens(
  accessToken: string,
  refreshToken: string,
  rememberMe = true,
): void {
  setRememberMe(rememberMe)
  const store = resolveStore(rememberMe)
  store.setItem(ACCESS_TOKEN_KEY, accessToken)
  store.setItem(REFRESH_TOKEN_KEY, refreshToken)
}

/**
 * 清除 access / refresh 两个令牌（登出）。
 */
export function clearTokens(): void {
  setAccessToken(null)
  setRefreshToken(null)
}
