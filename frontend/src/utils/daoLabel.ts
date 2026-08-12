/**
 * 大道 id → 中文标签；优先使用服务端下发的 label。
 */

/** 样本兜底映射（仅当服务端未给 label 时使用；禁止用此表做权威结算） */
const FALLBACK_DAO_LABELS: Record<string, string> = {
  dao_flame: '炎道',
  dao_flame_extreme: '炎极道',
  dao_frost: '霜道',
  dao_thunder: '雷道',
  dao_earth: '厚土道',
  dao_wind: '巽风道',
  dao_metal: '庚金道',
  dao_wood: '青木道',
  dao_water: '玄水道',
  dao_void: '虚空道',
}

/**
 * 解析道展示名。
 *
 * @param daoId - 道 id
 * @param serverLabel - 服务端 label（优先）
 */
export function daoLabel(
  daoId: string | null | undefined,
  serverLabel?: string | null,
): string {
  if (serverLabel) return serverLabel
  if (!daoId) return '—'
  if (daoId in FALLBACK_DAO_LABELS) return FALLBACK_DAO_LABELS[daoId]
  // §0.0.2：未知道不得裸出英文 id
  return `未知大道(${daoId})`
}

/**
 * 挑战结果中文。
 *
 * @param result - 结果枚举
 * @param serverLabel - 服务端文案优先
 */
export function daoChallengeResultLabel(
  result: string | null | undefined,
  serverLabel?: string | null,
): string {
  if (serverLabel) return serverLabel
  switch (result) {
    case 'challenger_win':
      return '挑战者胜 · 道主易主'
    case 'lord_win':
      return '道主守成'
    case 'abort':
      return '挑战者弃权'
    case 'disconnect_loss':
      return '断线判负'
    default:
      return result ? `结果：${result}` : '—'
  }
}
