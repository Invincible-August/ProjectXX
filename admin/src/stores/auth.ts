/**
 * 后台会话 Pinia。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchAdminMe, loginAdmin } from '../api/auth'
import { getAdminToken, setAdminToken } from '../api/http'
import type { AdminUserInfo } from '../types/api'

export const useAdminAuthStore = defineStore('adminAuth', () => {
  const user = ref<AdminUserInfo | null>(null)
  const bootstrapped = ref(false)

  const isLoggedIn = computed(() => Boolean(getAdminToken()) && Boolean(user.value))

  async function bootstrap() {
    const token = getAdminToken()
    if (!token) {
      bootstrapped.value = true
      return
    }
    try {
      user.value = await fetchAdminMe()
    } catch {
      setAdminToken(null)
      user.value = null
    } finally {
      bootstrapped.value = true
    }
  }

  async function login(username: string, password: string) {
    const data = await loginAdmin(username, password)
    setAdminToken(data.access_token)
    user.value = data.user
  }

  function logout() {
    setAdminToken(null)
    user.value = null
  }

  return { user, bootstrapped, isLoggedIn, bootstrap, login, logout }
})
