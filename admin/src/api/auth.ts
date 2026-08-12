/** 后台鉴权 API。 */
import { http, unwrap } from './http'
import type { AdminUserInfo } from '../types/api'

export async function loginAdmin(username: string, password: string) {
  return unwrap<{
    access_token: string
    token_type: string
    expires_in: number
    user: AdminUserInfo
  }>(http.post('/auth/login', { username, password }))
}

export async function fetchAdminMe() {
  return unwrap<AdminUserInfo>(http.get('/auth/me'))
}
