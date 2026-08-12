/**
 * 登录后 redirect 安全校验：仅允许站内已知路径，防止开放重定向。
 */

/** 允许作为登录后跳转目标的站内路径（精确匹配或前缀） */
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
  // M7 宗门 / 社交 / 经济
  '/sect',
  '/market',
  '/social',
  '/friends',
  '/party',
  '/dual-cultivation',
  '/shop',
])

/**
 * 校验并规范化 redirect 查询参数。
 *
 * @param raw - 查询参数中的 redirect 原文
 * @returns 合法站内 path（可含 query）；不合法则为 null
 */
export function resolveSafeRedirect(raw: unknown): string | null {
  if (typeof raw !== 'string' || !raw) return null
  const trimmed = raw.trim()
  if (!trimmed.startsWith('/') || trimmed.startsWith('//')) return null
  if (trimmed.includes('://')) return null

  // 拆出 path 与 query；只校验 path 段
  const qIndex = trimmed.indexOf('?')
  const pathOnly = qIndex >= 0 ? trimmed.slice(0, qIndex) : trimmed
  const normalized =
    pathOnly.length > 1 && pathOnly.endsWith('/')
      ? pathOnly.slice(0, -1)
      : pathOnly

  if (!ALLOWED_REDIRECT_PATHS.has(normalized)) return null
  return trimmed
}
