/**
 * 登录后 redirect 安全校验：仅允许站内已知路径，防止开放重定向。
 */
import type { RouteLocationRaw } from 'vue-router'

/** 允许作为登录后跳转目标的站内路径（精确匹配） */
const ALLOWED_REDIRECT_PATHS = new Set([
  '/hall',
  '/create-character',
  '/test',
  // M3 玩法路由
  '/formation',
  '/battle',
  // M4 双线程路由
  '/avatar',
  '/workshop',
  '/pets',
  // M5 环境与轮回
  '/tribulation',
  '/reincarnation',
  // M6 大道与道主
  '/dao',
  '/dao-lord',
  '/dao-lord/arena',
  // M7 宗门 / 社交 / 经济
  '/sect',
  '/market',
  '/social',
  '/friends',
  '/party',
  '/dual-cultivation',
  '/shop',
  '/account',
  '/character',
])

const LAST_PATH_KEY = 'xiuxian_last_play_path'

/**
 * 校验并规范化 redirect 查询参数。
 *
 * @param raw - 查询参数中的 redirect 原文
 * @returns 合法站内 path（可含 query）；不合法则为 null
 */
export function resolveSafeRedirect(raw: unknown): string | null {
  if (typeof raw !== 'string' || !raw) return null
  let trimmed = raw.trim()
  // 兼容被二次编码的 redirect
  try {
    if (trimmed.includes('%')) {
      trimmed = decodeURIComponent(trimmed)
    }
  } catch {
    // 保持原串
  }
  if (!trimmed.startsWith('/') || trimmed.startsWith('//')) return null
  if (trimmed.includes('://')) return null

  const qIndex = trimmed.indexOf('?')
  const pathOnly = qIndex >= 0 ? trimmed.slice(0, qIndex) : trimmed
  const normalized =
    pathOnly.length > 1 && pathOnly.endsWith('/')
      ? pathOnly.slice(0, -1)
      : pathOnly

  if (!ALLOWED_REDIRECT_PATHS.has(normalized)) return null
  return trimmed
}

/**
 * 将安全 redirect 字符串拆成 Vue Router location（正确带上 query）。
 *
 * 注意：不可把 ``/social?mode=party`` 整段塞进 ``{ path }``，否则会匹配失败并落到默认大厅。
 *
 * @param raw - 已通过或待校验的 redirect
 * @returns 路由 location；非法则为 null
 */
export function redirectToLocation(raw: unknown): RouteLocationRaw | null {
  const safe = resolveSafeRedirect(raw)
  if (!safe) return null
  const qIndex = safe.indexOf('?')
  if (qIndex < 0) return { path: safe }
  const path = safe.slice(0, qIndex)
  const query: Record<string, string> = {}
  const params = new URLSearchParams(safe.slice(qIndex + 1))
  params.forEach((value, key) => {
    query[key] = value
  })
  return { path, query }
}

/**
 * 清除记住的玩法路径（登出 / 登录落地大厅时调用）。
 */
export function clearLastPlayPath(): void {
  try {
    sessionStorage.removeItem(LAST_PATH_KEY)
  } catch {
    // ignore
  }
}

/**
 * 记住最近一次玩法路径（会话级；关标签清空）。
 * 注意：重新登录不再用此回跳，默认进大厅。
 *
 * @param fullPath - ``route.fullPath``
 */
export function rememberLastPlayPath(fullPath: string): void {
  const safe = resolveSafeRedirect(fullPath)
  if (!safe) return
  // 登录/创角/账号中心本身不记，避免回环或盖住真实玩法页
  const pathOnly = safe.split('?', 1)[0]
  if (
    pathOnly === '/login' ||
    pathOnly === '/register' ||
    pathOnly === '/create-character' ||
    pathOnly === '/account'
  ) {
    return
  }
  try {
    sessionStorage.setItem(LAST_PATH_KEY, safe)
  } catch {
    // 隐私模式等忽略
  }
}

/**
 * 读取并消费「上次玩法页」（兼容旧逻辑；登录已不再依赖）。
 *
 * @returns 安全 fullPath 或 null
 */
export function consumeLastPlayPath(): string | null {
  try {
    const raw = sessionStorage.getItem(LAST_PATH_KEY)
    if (!raw) return null
    sessionStorage.removeItem(LAST_PATH_KEY)
    return resolveSafeRedirect(raw)
  } catch {
    return null
  }
}

/**
 * 仅读取上次玩法页（不消费；根路径分流用）。
 */
export function peekLastPlayPath(): string | null {
  try {
    return resolveSafeRedirect(sessionStorage.getItem(LAST_PATH_KEY))
  } catch {
    return null
  }
}
