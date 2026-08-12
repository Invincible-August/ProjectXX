/**
 * 聊天坞道号颜色：按发言者大境界区分，正文固定黑色。
 *
 * 色阶由低到高递进，避免与正文黑字撞色。
 */

/** 大境界 key → 道号色（十六进制）。 */
const MAJOR_REALM_NAME_COLORS: Record<string, string> = {
  body_tempering: '#5a6b5a',
  qi_refining: '#2e7d32',
  foundation: '#1565c0',
  jindan: '#6a1b9a',
  yuanying: '#e65100',
  huashen: '#c62828',
  true_immortal: '#b8860b',
}

/** 未知境界或系统缺省时的道号色。 */
const FALLBACK_NAME_COLOR = '#37474f'

/**
 * 按大境界返回聊天道号 CSS 颜色。
 *
 * @param majorRealm - 后端 `sender_major_realm`（如 `foundation`）
 * @returns CSS color 字符串
 */
export function chatNameColorByMajorRealm(
  majorRealm: string | null | undefined,
): string {
  const key = String(majorRealm || '').trim()
  if (!key) return FALLBACK_NAME_COLOR
  return MAJOR_REALM_NAME_COLORS[key] ?? FALLBACK_NAME_COLOR
}

/**
 * 是否为「进入频道」类系统提示（聊天坞不展示）。
 *
 * @param bodyZh - 消息正文
 */
export function isChannelJoinNotice(bodyZh: string | null | undefined): boolean {
  const text = String(bodyZh || '').trim()
  if (!text) return false
  return /进入(了)?(本|该)?频道|加入(了)?(本|该)?频道|进入了聊天/.test(text)
}
