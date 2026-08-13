/**
 * 解析后端 UTC 时间串：无时区时按 UTC，避免被浏览器当地时区误判导致「已超时」。
 *
 * @param raw - ISO 时间或 null
 * @returns epoch ms；非法为 NaN
 */
export function parseUtcMs(raw: string | null | undefined): number {
  if (!raw) return Number.NaN
  const s = String(raw).trim()
  if (!s) return Number.NaN
  // 已有 Z / ±offset
  if (/[zZ]$/.test(s) || /[+-]\d{2}:\d{2}$/.test(s)) {
    return Date.parse(s)
  }
  // naive → 当作 UTC
  return Date.parse(`${s}Z`)
}
