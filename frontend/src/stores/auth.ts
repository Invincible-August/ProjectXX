/**
 * 鉴权 Pinia store：持有双令牌与当前用户，支持从 Storage 恢复登录态。
 *
 * 登录 / refresh 响应直接携带 ``has_character``，无需仅为分流再打 /me；
 * 刷新页面仍走 ``ensureSession`` → ``/auth/me``。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchMeApi, loginApi, refreshApi } from '../api/auth'
import type { AuthUser, LoginPayload, TokenPayload } from '../types/auth'
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  getRememberMe,
  persistTokens,
  setAccessToken,
  setRefreshToken,
} from '../utils/storage'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(null)
  const refreshToken = ref<string | null>(null)
  const user = ref<AuthUser | null>(null)
  /** 是否已创角；null 表示尚未从登录/refresh/me 获知 */
  const hasCharacter = ref<boolean | null>(null)
  /** 是否正在用 refresh 换票，避免并发 401 打出多次 refresh */
  const refreshing = ref(false)

  /**
   * 应用启动时从 Storage 恢复令牌（不主动请求 /me，由路由守卫或页面按需拉取）。
   */
  function loadFromStorage(): void {
    accessToken.value = getAccessToken()
    refreshToken.value = getRefreshToken()
  }

  /**
   * 当前 Storage / 内存中是否仍有任一令牌（用于守卫快速判断）。
   */
  function hasStoredTokens(): boolean {
    return Boolean(
      accessToken.value ||
        refreshToken.value ||
        getAccessToken() ||
        getRefreshToken(),
    )
  }

  /**
   * 将用户字段写入 store；换账号时作废旧创角缓存。
   *
   * @param data - 含 id / email / phone / display_name 的对象
   */
  function applyUser(data: {
    id: number
    email: string | null
    phone: string | null
    display_name: string
  }): void {
    if (user.value?.id !== data.id) {
      hasCharacter.value = null
    }
    user.value = {
      id: data.id,
      email: data.email,
      phone: data.phone,
      display_name: data.display_name,
    }
  }

  /**
   * 应用登录 / refresh 成功载荷：令牌 + 用户 + has_character。
   *
   * @param data - 后端 TokenPayload
   * @param rememberMe - 是否写入 localStorage（仅登录时有意义；refresh 用已存偏好）
   */
  function applyTokenPayload(data: TokenPayload, rememberMe: boolean): void {
    persistTokens(data.access_token, data.refresh_token, rememberMe)
    accessToken.value = data.access_token
    refreshToken.value = data.refresh_token
    if (data.user) applyUser(data.user)
    // 兼容旧后端：缺字段时保持 null，交给 ensureSession 拉 /me
    if (typeof data.has_character === 'boolean') {
      hasCharacter.value = data.has_character
    }
  }

  /**
   * 根据是否已创角返回登录后默认落地路径。
   * M5 状态分流（待引渡/渡劫）由路由守卫在拉取角色后覆盖。
   *
   * @returns `/hall` 或 `/create-character`
   */
  function homePathAfterAuth(): string {
    return hasCharacter.value ? '/hall' : '/create-character'
  }

  /**
   * 手动同步创角状态（创角成功 / 拉角色失败时由 character store 调用）。
   *
   * @param value - 是否已有角色
   */
  function setHasCharacter(value: boolean): void {
    hasCharacter.value = value
  }

  /**
   * 登录：调接口 → 按 rememberMe 持久化 → 写入 user 与 has_character。
   *
   * @param payload - 密码登录或短信登录载荷
   */
  async function login(payload: LoginPayload): Promise<void> {
    const envelope = await loginApi(payload)
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || `登录失败（code=${envelope.code}）`)
    }
    applyTokenPayload(envelope.data, payload.remember_me)
    // 旧后端未返回 has_character 时回退拉 /me
    if (hasCharacter.value === null) {
      const meOk = await fetchMe()
      if (!meOk) {
        throw new Error('登录成功但无法获取账号资料，请重试')
      }
    }
  }

  /**
   * 用 refresh 换新令牌；成功后更新 Storage 与内存（含 has_character）。
   *
   * @returns 是否刷新成功
   */
  async function refreshTokens(): Promise<boolean> {
    const currentRefresh = refreshToken.value || getRefreshToken()
    if (!currentRefresh) return false
    if (refreshing.value) return false
    refreshing.value = true
    try {
      const envelope = await refreshApi(currentRefresh)
      if (envelope.code !== 0 || !envelope.data) {
        logout()
        return false
      }
      applyTokenPayload(envelope.data, getRememberMe())
      return true
    } catch {
      logout()
      return false
    } finally {
      refreshing.value = false
    }
  }

  /**
   * 拉取 /auth/me 并写入 user / hasCharacter；access 失效时尝试 refresh 一次。
   *
   * @returns 是否拿到有效用户
   */
  async function fetchMe(): Promise<boolean> {
    if (!getAccessToken() && !getRefreshToken()) return false
    try {
      const envelope = await fetchMeApi()
      if (envelope.code === 0 && envelope.data) {
        applyUser(envelope.data)
        hasCharacter.value = envelope.data.has_character
        return true
      }
    } catch {
      // 下方走 refresh 重试
    }
    const ok = await refreshTokens()
    if (!ok) return false
    // refresh 已写入 has_character 时可直接成功；否则再拉 /me
    if (user.value && hasCharacter.value !== null) return true
    const retry = await fetchMeApi()
    if (retry.code === 0 && retry.data) {
      applyUser(retry.data)
      hasCharacter.value = retry.data.has_character
      return true
    }
    return false
  }

  /**
   * 确保会话有效：有 token 时必要时拉 /me；失败则登出。
   *
   * @returns 是否已处于有效登录态
   */
  async function ensureSession(): Promise<boolean> {
    if (!hasStoredTokens()) return false
    if (user.value && hasCharacter.value !== null) return true
    const ok = await fetchMe()
    if (!ok) {
      logout()
      return false
    }
    return true
  }

  /** 清除内存与 Storage 中的登录态。 */
  function logout(): void {
    accessToken.value = null
    refreshToken.value = null
    user.value = null
    hasCharacter.value = null
    clearTokens()
    setAccessToken(null)
    setRefreshToken(null)
    void import('./character').then(({ useCharacterStore }) => {
      useCharacterStore().clear()
    })
    // M3：战报零保留——登出即清空本会话战报
    void import('./battle').then(({ useBattleStore }) => {
      useBattleStore().clearOnLogout()
    })
    // M5：清空环境 / 渡劫 / 引渡内存态
    void import('./world').then(({ useWorldStore }) => {
      useWorldStore().clear()
    })
    void import('./tribulation').then(({ useTribulationStore }) => {
      useTribulationStore().clear()
    })
    void import('./ferry').then(({ useFerryStore }) => {
      useFerryStore().clear()
    })
    // M7：退出登录清空本会话聊天与机缘本地态（未抢完机缘下次进房仍会拉回）
    void import('./chat').then(({ useChatStore }) => {
      useChatStore().clearSession()
    })
  }

  return {
    accessToken,
    refreshToken,
    user,
    hasCharacter,
    loadFromStorage,
    hasStoredTokens,
    homePathAfterAuth,
    setHasCharacter,
    applyTokenPayload,
    login,
    logout,
    refreshTokens,
    fetchMe,
    ensureSession,
  }
})
