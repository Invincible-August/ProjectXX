/**
 * 挂机方向中文标签（本体 / 化身 / 大厅共用）。
 * 机读英文 id；人读中文（开发计划 §0.0.2）。
 */

/** 方向 key → 短标签 */
export const IDLE_DIRECTION_LABELS: Record<string, string> = {
  none: '停止',
  spirit: '修炼',
  body: '淬体',
  crafting: '制造业修炼',
  sect_mining: '采矿',
}

/**
 * 取挂机方向中文名。
 *
 * 参数:
 * - direction: 方向 key
 * - fallback: 未知时回退（默认「未知」，禁止回落裸英文 id）
 */
export function idleDirectionLabel(direction: string, fallback?: string): string {
  return IDLE_DIRECTION_LABELS[direction] ?? fallback ?? `未知(${direction})`
}

/**
 * 大厅化身角标文案。
 */
export function avatarIdleBadge(direction: string | undefined, hasAvatar: boolean): string {
  if (!hasAvatar) return '未凝练'
  const dir = direction ?? 'none'
  if (dir === 'none') return '待机'
  if (dir === 'spirit') return '修炼中'
  if (dir === 'body') return '淬体中'
  if (dir === 'crafting') return '制造业修炼中'
  if (dir === 'sect_mining') return '采矿中'
  return idleDirectionLabel(dir)
}
