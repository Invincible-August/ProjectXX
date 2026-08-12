/**
 * 挂机「本周天预计」客户端计算（仅展示，不写库、不请求服务器）。
 *
 * 公式对齐后端：
 * ``effective = floor(base * channel_mult * clamp(tagProduct * shichen * weather))``
 *
 * 时辰/天气乘区取自 ``/world/env.idle_preview``（世界轮询已有）；
 * 灵根/功法标签与体质等通道在环境未变时沿用 ``character.idle_env`` 拆解。
 */

import type { CharacterPublic } from '../types/character'
import type { IdleDirectionEnvPreview, IdleEnvBundle } from '../types/idleEnv'

const CLAMP_MIN = 0.5
const CLAMP_MAX = 1.5

/** 内部/外部加成通道 source（不含环境与境界基础） */
const CHANNEL_SOURCES = new Set([
  'constitution',
  'equipment',
  'buff_pill',
  'buff_talisman',
  'spirit_eye',
  'cave',
])

/**
 * Clamp multiplier into ``[min, max]``（与后端 env clamp 一致）。
 *
 * @param value - Raw product
 * @param minValue - Lower bound
 * @param maxValue - Upper bound
 */
export function clampIdleMult(
  value: number,
  minValue: number = CLAMP_MIN,
  maxValue: number = CLAMP_MAX,
): number {
  return Math.max(minValue, Math.min(maxValue, value))
}

/**
 * 来源文案（与 IdleEnvPanel 对齐，供调试/复用）。
 *
 * @param source - breakdown.source
 */
export function idleSourceLabel(source: string): string {
  const map: Record<string, string> = {
    realm_base: '境界基础',
    shichen: '时辰',
    weather: '天气',
    tag_shichen: '灵根/功法·时辰',
    tag_weather: '灵根/功法·天气',
    constitution: '体质',
    equipment: '装备',
    buff_pill: '丹药buff',
    buff_talisman: '符箓buff',
    spirit_eye: '灵眼',
    cave: '洞府',
  }
  return map[source] || source
}

/**
 * 从 breakdown 取指定 source 的乘区；缺失为 1。
 *
 * @param preview - 方向预览
 * @param source - shichen | weather | …
 */
export function multFromBreakdown(
  preview: IdleDirectionEnvPreview | null | undefined,
  source: string,
): number {
  if (!preview?.breakdown?.length) return 1
  const row = preview.breakdown.find((b) => b.source === source)
  const m = row?.mult
  return typeof m === 'number' && Number.isFinite(m) ? m : 1
}

/**
 * 汇总仍适用于「当前」时辰/天气的标签乘区。
 *
 * @param characterDir - 角色上次 idle_env 该方向预览（可含过期环境）
 * @param currentShichen - 世界当前时辰 id
 * @param currentWeather - 世界当前天气 id
 */
export function tagProductForCurrentEnv(
  characterDir: IdleDirectionEnvPreview | null | undefined,
  currentShichen: string | null | undefined,
  currentWeather: string | null | undefined,
): number {
  if (!characterDir?.breakdown?.length) return 1
  let product = 1
  const shichenId = characterDir.shichen?.id
  const weatherId = characterDir.weather?.id
  for (const row of characterDir.breakdown) {
    if (row.source === 'tag_shichen') {
      // 仅当时辰未变时沿用标签×时辰乘区，避免错用旧时辰表
      if (currentShichen && shichenId && shichenId !== currentShichen) continue
      product *= Number.isFinite(row.mult) ? row.mult : 1
    } else if (row.source === 'tag_weather') {
      if (currentWeather && weatherId && weatherId !== currentWeather) continue
      product *= Number.isFinite(row.mult) ? row.mult : 1
    }
  }
  return product
}

/**
 * 从角色 idle_env 拆解汇总通道乘区（体质/装备/buff/驻地）。
 *
 * @param characterDir - 角色方向预览
 */
export function channelProductFromBreakdown(
  characterDir: IdleDirectionEnvPreview | null | undefined,
): number {
  if (!characterDir?.breakdown?.length) return 1
  let product = 1
  for (const row of characterDir.breakdown) {
    if (!CHANNEL_SOURCES.has(row.source)) continue
    product *= Number.isFinite(row.mult) ? row.mult : 1
  }
  return product
}

/**
 * 计算某方向本周天有效产出（整数，与后端 int(base*channel*env) 对齐）。
 *
 * @param basePerTick - 角色面板基础速率（idle_*_per_tick，已为境界表）
 * @param worldDir - 世界 idle_preview 该方向（无角色标签）
 * @param characterDir - 角色 idle_env 该方向（可含标签与通道）
 * @param currentShichen - 当前时辰
 * @param currentWeather - 当前天气
 */
export function computeEffectivePerTick(
  basePerTick: number,
  worldDir: IdleDirectionEnvPreview | null | undefined,
  characterDir: IdleDirectionEnvPreview | null | undefined,
  currentShichen: string | null | undefined,
  currentWeather: string | null | undefined,
): number {
  const base = Math.max(0, Math.floor(Number(basePerTick) || 0))
  if (base <= 0) return 0

  // 环境与角色预览一致时，直接用权威 effective（含标签与通道）
  if (
    characterDir &&
    currentShichen &&
    currentWeather &&
    characterDir.shichen?.id === currentShichen &&
    characterDir.weather?.id === currentWeather
  ) {
    return Math.max(0, Math.floor(characterDir.effective_per_tick))
  }

  const shichenMult = multFromBreakdown(worldDir ?? characterDir, 'shichen')
  const weatherMult = multFromBreakdown(worldDir ?? characterDir, 'weather')
  const tagProduct = tagProductForCurrentEnv(
    characterDir,
    currentShichen,
    currentWeather,
  )
  const envMult = clampIdleMult(tagProduct * shichenMult * weatherMult)
  const channelMult = channelProductFromBreakdown(characterDir)
  return Math.max(0, Math.floor(base * channelMult * envMult))
}

export type IdleGainDirection = 'spirit' | 'body' | 'crafting' | 'none' | string

/**
 * 按当前挂机方向取基础速率。
 *
 * @param character - 权威角色
 * @param direction - 方向（默认读 character.idle_direction）
 */
export function baseGainForDirection(
  character: CharacterPublic,
  direction?: IdleGainDirection,
): number {
  const dir = direction ?? character.idle_direction
  if (dir === 'spirit') return character.idle_cultivation_per_tick
  if (dir === 'body') return character.idle_body_per_tick ?? 0
  if (dir === 'crafting') return character.idle_crafting_per_tick ?? 0
  if (dir === 'sect_mining') {
    return character.idle_env?.sect_mining?.base_per_tick ?? 0
  }
  return 0
}

/**
 * 本周天预计有效产出（浏览器实时计算）。
 *
 * @param character - 权威角色
 * @param worldIdlePreview - `/world/env.idle_preview`
 * @param shichen - 当前时辰 id
 * @param weather - 当前天气 id
 * @param direction - 覆盖方向；默认本体 idle_direction
 */
export function computeTickGainForDirection(
  character: CharacterPublic,
  worldIdlePreview: IdleEnvBundle | null | undefined,
  shichen: string | null | undefined,
  weather: string | null | undefined,
  direction?: IdleGainDirection,
): number {
  const dir = direction ?? character.idle_direction
  if (
    dir !== 'spirit' &&
    dir !== 'body' &&
    dir !== 'crafting' &&
    dir !== 'sect_mining'
  ) {
    return 0
  }
  const base = baseGainForDirection(character, dir)
  const worldDir =
    dir === 'sect_mining'
      ? worldIdlePreview?.sect_mining
      : worldIdlePreview?.[dir as 'spirit' | 'body' | 'crafting']
  const characterDir =
    dir === 'sect_mining'
      ? character.idle_env?.sect_mining
      : character.idle_env?.[dir as 'spirit' | 'body' | 'crafting']
  return computeEffectivePerTick(base, worldDir, characterDir, shichen, weather)
}

/**
 * 「本周天预计」展示文案。
 *
 * @param character - 权威角色
 * @param worldIdlePreview - 世界挂机预览
 * @param shichen - 当前时辰
 * @param weather - 当前天气
 * @param direction - 方向
 */
export function formatTickGainLabel(
  character: CharacterPublic,
  worldIdlePreview: IdleEnvBundle | null | undefined,
  shichen: string | null | undefined,
  weather: string | null | undefined,
  direction?: IdleGainDirection,
): string {
  const dir = direction ?? character.idle_direction
  const rate = computeTickGainForDirection(
    character,
    worldIdlePreview,
    shichen,
    weather,
    dir,
  )
  if (dir === 'spirit') return `修为 +${rate}`
  if (dir === 'body') return `淬体度 +${rate}`
  if (dir === 'crafting') return `制造业经验 +${rate}`
  if (dir === 'sect_mining') return `个人灵石 +${rate}`
  return ''
}
