/**
 * 将后端渡劫会话字段归一为前端 TribulationSessionPublic。
 * 兼容 target_display / power_tier_label / veil_chosen 等别名。
 */
import type { TribulationSessionPublic } from '../types/tribulation'

/**
 * 安全取有限数字，缺省为 fallback。
 *
 * @param value - 原始值
 * @param fallback - 缺省
 */
export function finiteNumber(value: unknown, fallback = 0): number {
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? n : fallback
}

/**
 * 解包并归一渡劫会话。
 *
 * @param raw - API data 或 session 本体（可能包在 { session } 内）
 * @returns 归一后的会话；无会话则 null
 */
export function normalizeTribulationSession(
  raw: unknown,
): TribulationSessionPublic | null {
  if (raw == null || typeof raw !== 'object') return null
  const bag = raw as Record<string, unknown>
  // GET /me 形如 { session: {...} }；mutation 已是 session 本体
  const src =
    bag.session != null && typeof bag.session === 'object' && !('phase' in bag)
      ? (bag.session as Record<string, unknown>)
      : 'phase' in bag || 'strike_total' in bag || 'id' in bag
        ? bag
        : (bag.session as Record<string, unknown> | undefined)

  if (src == null || typeof src !== 'object') return null

  const powerLabel = String(
    src.power_label ?? src.power_tier_label ?? src.power_tier ?? '',
  )
  const countLabel = String(
    src.count_label ?? src.count_tier_label ?? src.count_tier ?? '',
  )
  const targetLabel = String(
    src.target_label ?? src.target_display ?? '',
  )
  const veilSelected = Boolean(src.veil_selected ?? src.veil_chosen ?? false)
  const displayWeather = (src.display_weather ??
    (src.phase === 'running' ? 'tribulation_cloud' : src.locked_weather) ??
    'clear') as TribulationSessionPublic['display_weather']

  return {
    id: finiteNumber(src.id, 0),
    phase: (src.phase as TribulationSessionPublic['phase']) || 'preparing',
    target_label: targetLabel,
    projected_grade: (src.projected_grade_name as string | undefined) ??
      (src.projected_grade as string | undefined),
    power_tier: (src.power_tier as TribulationSessionPublic['power_tier']) || 'normal',
    power_label: powerLabel,
    count_tier: (src.count_tier as TribulationSessionPublic['count_tier']) || 'nine',
    count_label: countLabel,
    strike_total: finiteNumber(src.strike_total, 0),
    strike_done: finiteNumber(src.strike_done, 0),
    locked_shichen: (src.locked_shichen as TribulationSessionPublic['locked_shichen']) || 'noon',
    locked_weather: (src.locked_weather as TribulationSessionPublic['locked_weather']) || 'clear',
    locked_weather_label: src.locked_weather_label as string | undefined,
    display_weather: displayWeather,
    in_cloud_double: Boolean(src.in_cloud_double),
    cloud_radius: finiteNumber(src.cloud_radius, 0),
    hp_current: finiteNumber(src.hp_current, 0),
    hp_max: finiteNumber(src.hp_max, 1),
    prep_slots: Array.isArray(src.prep_slots)
      ? (src.prep_slots as TribulationSessionPublic['prep_slots'])
      : [],
    formation_id: (src.formation_id as string | null | undefined) ?? null,
    veil_selected: veilSelected,
    veil_result: (src.veil_result as TribulationSessionPublic['veil_result']) ?? null,
    guardian_used: Boolean(src.guardian_used),
    axis_hints: src.axis_hints as TribulationSessionPublic['axis_hints'],
    batch_log: src.batch_log as string[] | undefined,
    fate_luck: src.fate_luck as number | undefined,
    demonic_nature: src.demonic_nature as number | undefined,
  }
}
