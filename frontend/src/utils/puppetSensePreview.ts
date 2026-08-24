/**
 * 傀儡神识发挥预览（仅展示）。
 *
 * 对齐后端 ``app.domain.divine_sense.puppet_sense_reading``：
 * ``load <= soft_cap`` → 100%；否则按 load/capacity 匹配 ``overload_bands``。
 * 不在前端另写曲线。
 */

import type { PuppetSenseBand, PuppetSensePublic } from '../types/equipment'

export interface PuppetSensePreview {
  load: number
  percent: number
  zone: string
  zone_label_zh: string
}

function loadRatio(load: number, capacity: number): number {
  if (capacity <= 0) {
    return load > 0 ? 999 : 0
  }
  return load / capacity
}

/**
 * Compute puppet-sense preview from a pending load and server bands.
 *
 * @param load - Sum of selected puppet costs
 * @param spec - Payload from GET /equipment/slots.puppet_sense
 */
export function puppetSenseFromLoad(
  load: number,
  spec: PuppetSensePublic | null | undefined,
): PuppetSensePreview {
  const safeLoad = Math.max(0, Math.floor(load))
  if (!spec) {
    return { load: safeLoad, percent: 100, zone: 'comfort', zone_label_zh: '舒适区' }
  }
  if (safeLoad <= spec.soft_cap) {
    const comfort = spec.bands.find((b) => b.zone === 'comfort')
    return {
      load: safeLoad,
      percent: 100,
      zone: 'comfort',
      zone_label_zh: comfort?.zone_label_zh || '舒适区',
    }
  }
  const ratio = loadRatio(safeLoad, spec.capacity)
  const finite = spec.bands
    .filter((b): b is PuppetSenseBand & { max_load_ratio: number } => b.max_load_ratio != null)
    .slice()
    .sort((a, b) => a.max_load_ratio - b.max_load_ratio)
  for (const band of finite) {
    if (ratio <= band.max_load_ratio) {
      return {
        load: safeLoad,
        percent: Math.round(band.combat_stat_mult * 100),
        zone: band.zone,
        zone_label_zh: band.zone_label_zh,
      }
    }
  }
  const catchAll = [...spec.bands].reverse().find((b) => b.max_load_ratio == null)
  if (catchAll) {
    return {
      load: safeLoad,
      percent: Math.round(catchAll.combat_stat_mult * 100),
      zone: catchAll.zone,
      zone_label_zh: catchAll.zone_label_zh,
    }
  }
  return {
    load: safeLoad,
    percent: 100,
    zone: 'comfort',
    zone_label_zh: '舒适区',
  }
}
