/**
 * 大境界序（与后端 reincarnation_rules 默认链对齐；仅用于入口显隐）。
 * 开道门槛以服务端 40080 为准。
 */
const MAJOR_ORDER = [
  'body_tempering',
  'qi_refining',
  'foundation',
  'jindan',
  'yuanying',
  'huashen',
  'true_immortal',
] as const

/**
 * 当前大境界是否达到门槛。
 *
 * @param current - 角色或化身 major_realm
 * @param minMajor - 最低大境界 id
 */
export function meetsMinMajor(
  current: string | null | undefined,
  minMajor: string,
): boolean {
  const need = MAJOR_ORDER.indexOf(minMajor as (typeof MAJOR_ORDER)[number])
  if (need < 0) return true
  const have = MAJOR_ORDER.indexOf((current || '') as (typeof MAJOR_ORDER)[number])
  return have >= need
}

/** 悟道页 / 入口：须真仙。 */
export function canEnterWudao(majorRealm: string | null | undefined): boolean {
  return meetsMinMajor(majorRealm, 'true_immortal')
}
