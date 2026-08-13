/**
 * 灵石 / 炉鼎小时等：仅接受非负整数。
 */

/**
 * 解析非负整数；非法则返回 null。
 *
 * @param value - 任意输入
 * @returns 整数或 null
 */
export function parseNonNegInt(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'boolean') return null
  if (typeof value === 'number') {
    if (!Number.isFinite(value) || !Number.isInteger(value) || value < 0) return null
    return value
  }
  if (typeof value === 'string') {
    const text = value.trim()
    if (!/^\d+$/.test(text)) return null
    const n = Number(text)
    if (!Number.isSafeInteger(n) || n < 0) return null
    return n
  }
  return null
}

/**
 * 强制非负整数；非法抛错或回退。
 *
 * @param value - 输入
 * @param fallback - 非法时回退（默认抛错用 Error）
 */
export function requireNonNegInt(value: unknown, fallback?: number): number {
  const n = parseNonNegInt(value)
  if (n !== null) return n
  if (fallback !== undefined) return fallback
  throw new Error('须为 ≥ 0 的整数')
}
