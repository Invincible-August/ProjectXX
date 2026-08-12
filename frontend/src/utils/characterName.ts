/**
 * 角色名校验（与 M0 §3.4 / 后端 CreateCharacterRequest 一致）。
 *
 * @param name - 用户输入的角色名（会 trim）
 * @returns 错误文案；合法则返回 null
 */
export function validateCharacterName(name: string): string | null {
  const trimmed = name.trim()
  if (trimmed.length < 2 || trimmed.length > 16) {
    return '角色名长度须为 2～16 个字符'
  }
  if (!/^[\u4e00-\u9fa5a-zA-Z0-9]+$/.test(trimmed)) {
    return '角色名仅允许中文、字母与数字'
  }
  return null
}
