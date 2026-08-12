/**
 * 修炼客户端预测：按与服务端相同的 tick 公式推算展示值（不写库）。
 *
 * M2：spirit / body / crafting 均可产出对应池；片内条只驱动动画。
 * 境界进度条用权威 realm_progress，不跟挂机池预测。
 * 筑基前 idle_stones_per_tick=0：免费挂机，不得判为「灵石不足停滞」。
 */

import type { CharacterPublic } from '../types/character'

/** 面板展示用的预测快照 */
export interface IdleDisplaySnapshot {
  cultivation_points: number
  body_tempering_points: number
  crafting_exp: number
  spirit_stones: number
  /** 权威境界进度比例（不预测） */
  cultivation_progress_ratio: number
  is_stalled: boolean
  predicted_ticks: number
  tick_progress_ratio: number
  seconds_into_tick: number
  tick_seconds: number
}

/**
 * 解析 ISO 时间为 epoch ms；失败返回 NaN。
 *
 * @param iso - 服务端时间串
 */
export function parseUtcMs(iso: string): number {
  const ms = Date.parse(iso)
  return Number.isFinite(ms) ? ms : Number.NaN
}

/**
 * 是否处于可产出挂机方向（修灵/炼体/制造业；不含采矿）。
 *
 * @param direction - idle_direction
 */
export function isProductiveDirection(direction: string): boolean {
  return direction === 'spirit' || direction === 'body' || direction === 'crafting'
}

/**
 * 是否占用修炼态（含采矿挂机，与开战/工坊等互斥）。
 *
 * @param direction - idle_direction
 */
export function isIdleBusyDirection(direction: string): boolean {
  return isProductiveDirection(direction) || direction === 'sect_mining'
}

/**
 * 构造无片内进度的快照。
 */
function snapshotWithoutTickProgress(
  cultivation: number,
  body: number,
  crafting: number,
  stones: number,
  ratio: number,
  stalled: boolean,
  predictedTicks: number,
  tickSeconds: number,
): IdleDisplaySnapshot {
  return {
    cultivation_points: cultivation,
    body_tempering_points: body,
    crafting_exp: crafting,
    spirit_stones: stones,
    cultivation_progress_ratio: ratio,
    is_stalled: stalled,
    predicted_ticks: predictedTicks,
    tick_progress_ratio: 0,
    seconds_into_tick: 0,
    tick_seconds: tickSeconds,
  }
}

/**
 * 由已过去秒数推算本周天内进度（仅动画用）。
 *
 * @param elapsedSec - 相对 last_settled_at 的已过秒数
 * @param tickSeconds - 一周天时长（秒）
 */
export function computeTickProgress(
  elapsedSec: number,
  tickSeconds: number,
): { seconds_into_tick: number; tick_progress_ratio: number } {
  const safeTick = Math.max(1, tickSeconds)
  const into = Math.max(0, elapsedSec) % safeTick
  return {
    seconds_into_tick: into,
    tick_progress_ratio: Math.min(1, into / safeTick),
  }
}

/**
 * 当前方向每 tick 池增量（修为/炼体/制造业）。
 * 优先用调用方传入的环境修正速率；否则回退角色基础字段。
 *
 * @param character - 权威角色
 * @param envAwareRate - 前端实时算出的有效速率（可选）
 */
function poolGainPerTick(
  character: CharacterPublic,
  envAwareRate?: number | null,
): number {
  if (typeof envAwareRate === 'number' && Number.isFinite(envAwareRate)) {
    return Math.max(0, Math.floor(envAwareRate))
  }
  if (character.idle_direction === 'spirit') {
    return character.idle_cultivation_per_tick
  }
  if (character.idle_direction === 'body') {
    return character.idle_body_per_tick ?? 0
  }
  if (character.idle_direction === 'crafting') {
    return character.idle_crafting_per_tick ?? 0
  }
  return 0
}

/**
 * 按方向把 tick 产出加到对应池。
 */
function applyPoolGain(
  direction: string,
  gain: number,
  cultivation: number,
  body: number,
  crafting: number,
): { cultivation: number; body: number; crafting: number } {
  let nextCultivation = cultivation
  let nextBody = body
  let nextCrafting = crafting
  if (direction === 'spirit') nextCultivation += gain
  if (direction === 'body') nextBody += gain
  if (direction === 'crafting') nextCrafting += gain
  return {
    cultivation: nextCultivation,
    body: nextBody,
    crafting: nextCrafting,
  }
}

/**
 * 根据权威角色与当前时刻推算展示字段。
 *
 * @param character - 服务端权威角色
 * @param nowMs - 当前 epoch ms
 * @param envAwarePoolRate - 可选：浏览器算出的本周天有效产出（与「本周天预计」一致）
 */
export function predictIdleDisplay(
  character: CharacterPublic,
  nowMs: number = Date.now(),
  envAwarePoolRate?: number | null,
): IdleDisplaySnapshot {
  const baseCultivation = character.cultivation_points
  const baseBody = character.body_tempering_points
  const baseCrafting = character.crafting_exp
  const baseStones = character.spirit_stones
  const required = character.cultivation_to_next
  const tickSeconds = Math.max(1, character.idle_tick_seconds || 60)
  // 境界进度只读权威 realm_progress（分配后才涨）
  const realmRatio =
    required == null || required <= 0
      ? 0
      : Math.min(1, (character.realm_progress ?? 0) / required)

  // 采矿：仅驱动片内进度条；灵石/体力由服务端自开始锚点满 tick 结算（首段不扣）
  if (
    character.status === 'normal' &&
    character.idle_direction === 'sect_mining' &&
    !character.offline_pending
  ) {
    const lastMs = parseUtcMs(character.last_settled_at)
    if (!Number.isFinite(lastMs)) {
      return snapshotWithoutTickProgress(
        baseCultivation,
        baseBody,
        baseCrafting,
        baseStones,
        realmRatio,
        false,
        0,
        tickSeconds,
      )
    }
    const elapsedSec = Math.max(0, (nowMs - lastMs) / 1000)
    const progress = computeTickProgress(elapsedSec, tickSeconds)
    return {
      cultivation_points: baseCultivation,
      body_tempering_points: baseBody,
      crafting_exp: baseCrafting,
      spirit_stones: baseStones,
      cultivation_progress_ratio: realmRatio,
      is_stalled: false,
      predicted_ticks: 0,
      tick_progress_ratio: progress.tick_progress_ratio,
      seconds_into_tick: progress.seconds_into_tick,
      tick_seconds: tickSeconds,
    }
  }

  if (
    character.status !== 'normal' ||
    !isProductiveDirection(character.idle_direction) ||
    character.is_stalled ||
    character.offline_pending
  ) {
    return snapshotWithoutTickProgress(
      baseCultivation,
      baseBody,
      baseCrafting,
      baseStones,
      realmRatio,
      character.is_stalled || Boolean(character.offline_pending),
      0,
      tickSeconds,
    )
  }

  const ratePool = poolGainPerTick(character, envAwarePoolRate)
  const rateS = Math.max(0, character.idle_stones_per_tick)

  // 无产出：不动画，但不冒充「灵石不足」
  if (ratePool <= 0) {
    return snapshotWithoutTickProgress(
      baseCultivation,
      baseBody,
      baseCrafting,
      baseStones,
      realmRatio,
      false,
      0,
      tickSeconds,
    )
  }

  const lastMs = parseUtcMs(character.last_settled_at)
  if (!Number.isFinite(lastMs)) {
    return snapshotWithoutTickProgress(
      baseCultivation,
      baseBody,
      baseCrafting,
      baseStones,
      realmRatio,
      false,
      0,
      tickSeconds,
    )
  }

  const elapsedSec = Math.max(0, (nowMs - lastMs) / 1000)
  const maxTicks = Math.floor(elapsedSec / tickSeconds)
  const tickProg = computeTickProgress(elapsedSec, tickSeconds)

  // 筑基前免费：rateS===0 → 满 tick、不扣石、不停滞（与服务端 IdleGainCalculator 一致）
  const freeIdle = rateS <= 0

  if (maxTicks <= 0) {
    return {
      cultivation_points: baseCultivation,
      body_tempering_points: baseBody,
      crafting_exp: baseCrafting,
      spirit_stones: baseStones,
      cultivation_progress_ratio: realmRatio,
      is_stalled: false,
      predicted_ticks: 0,
      tick_progress_ratio: tickProg.tick_progress_ratio,
      seconds_into_tick: tickProg.seconds_into_tick,
      tick_seconds: tickSeconds,
    }
  }

  let used: number
  let stalled: boolean
  let stones: number
  if (freeIdle) {
    used = maxTicks
    stalled = false
    stones = baseStones
  } else {
    const affordable = Math.floor(baseStones / rateS)
    used = Math.min(maxTicks, affordable)
    stalled = affordable < maxTicks
    stones = baseStones - used * rateS
    if (stones < rateS) {
      stalled = true
    }
  }

  const gain = used * ratePool
  const pools = applyPoolGain(
    character.idle_direction,
    gain,
    baseCultivation,
    baseBody,
    baseCrafting,
  )

  if (stalled) {
    return snapshotWithoutTickProgress(
      pools.cultivation,
      pools.body,
      pools.crafting,
      stones,
      realmRatio,
      true,
      used,
      tickSeconds,
    )
  }

  return {
    cultivation_points: pools.cultivation,
    body_tempering_points: pools.body,
    crafting_exp: pools.crafting,
    spirit_stones: stones,
    cultivation_progress_ratio: realmRatio,
    is_stalled: false,
    predicted_ticks: used,
    tick_progress_ratio: tickProg.tick_progress_ratio,
    seconds_into_tick: tickProg.seconds_into_tick,
    tick_seconds: tickSeconds,
  }
}

/**
 * 化身线程片内进度预测（只读展示；权威仍由 settle_dual 入账）。
 *
 * @param character - 本体权威（灵石池 / 离线 pending / 片长）
 * @param nowMs - 当前 epoch ms
 */
export function predictAvatarIdleDisplay(
  character: CharacterPublic,
  nowMs: number = Date.now(),
): IdleDisplaySnapshot | null {
  if (!character.has_avatar || !character.avatar_summary) return null

  const summary = character.avatar_summary
  const preview = character.dual_idle_preview
  const direction =
    preview?.avatar_idle_direction ?? summary.idle_direction ?? 'none'
  const tickSeconds = Math.max(1, character.idle_tick_seconds || 60)
  const baseCultivation = summary.cultivation_points ?? 0
  const baseBody = summary.body_tempering_points ?? 0
  const baseCrafting = summary.crafting_exp ?? 0
  const baseStones = character.spirit_stones

  const rateCultivation = preview?.avatar_cultivation_per_tick ?? 0
  const rateBody = preview?.avatar_body_per_tick ?? 0
  const rateCrafting = preview?.avatar_crafting_per_tick ?? 0
  const ratePool =
    direction === 'spirit'
      ? rateCultivation
      : direction === 'body'
        ? rateBody
        : direction === 'crafting'
          ? rateCrafting
          : 0
  const rateS = Math.max(0, preview?.avatar_stones_per_tick ?? 0)

  const lastIso =
    preview?.avatar_last_settled_at ?? summary.last_settled_at ?? ''
  const stalledByPending = Boolean(character.offline_pending)
  if (!isProductiveDirection(direction) || stalledByPending || ratePool <= 0) {
    return snapshotWithoutTickProgress(
      baseCultivation,
      baseBody,
      baseCrafting,
      baseStones,
      0,
      stalledByPending,
      0,
      tickSeconds,
    )
  }

  const lastMs = parseUtcMs(lastIso)
  if (!Number.isFinite(lastMs)) {
    return snapshotWithoutTickProgress(
      baseCultivation,
      baseBody,
      baseCrafting,
      baseStones,
      0,
      false,
      0,
      tickSeconds,
    )
  }

  const elapsedSec = Math.max(0, (nowMs - lastMs) / 1000)
  const maxTicks = Math.floor(elapsedSec / tickSeconds)
  const tickProg = computeTickProgress(elapsedSec, tickSeconds)
  const freeIdle = rateS <= 0

  if (maxTicks <= 0) {
    return {
      cultivation_points: baseCultivation,
      body_tempering_points: baseBody,
      crafting_exp: baseCrafting,
      spirit_stones: baseStones,
      cultivation_progress_ratio: 0,
      is_stalled: freeIdle ? false : baseStones < rateS,
      predicted_ticks: 0,
      tick_progress_ratio: tickProg.tick_progress_ratio,
      seconds_into_tick: tickProg.seconds_into_tick,
      tick_seconds: tickSeconds,
    }
  }

  let used: number
  let stalled: boolean
  let stones: number
  if (freeIdle) {
    used = maxTicks
    stalled = false
    stones = baseStones
  } else {
    const affordable = Math.floor(baseStones / rateS)
    used = Math.min(maxTicks, affordable)
    stalled = affordable < maxTicks
    stones = baseStones - used * rateS
    if (stones < rateS) stalled = true
  }

  const gain = used * ratePool
  const pools = applyPoolGain(direction, gain, baseCultivation, baseBody, baseCrafting)

  if (stalled) {
    return snapshotWithoutTickProgress(
      pools.cultivation,
      pools.body,
      pools.crafting,
      stones,
      0,
      true,
      used,
      tickSeconds,
    )
  }

  return {
    cultivation_points: pools.cultivation,
    body_tempering_points: pools.body,
    crafting_exp: pools.crafting,
    spirit_stones: stones,
    cultivation_progress_ratio: 0,
    is_stalled: false,
    predicted_ticks: used,
    tick_progress_ratio: tickProg.tick_progress_ratio,
    seconds_into_tick: tickProg.seconds_into_tick,
    tick_seconds: tickSeconds,
  }
}

/**
 * 根据权威角色或服务端 next_tick_at 推算下次对齐时刻（epoch ms）。
 *
 * @param character - 权威角色
 * @param nextTickAt - 服务端提示；可空
 */
export function resolveNextDueMs(
  character: CharacterPublic | null,
  nextTickAt: string | null | undefined,
): number | null {
  if (!character) return null
  if (!isIdleBusyDirection(character.idle_direction) || character.status !== 'normal') {
    return null
  }
  if (
    (isProductiveDirection(character.idle_direction) && character.is_stalled) ||
    character.offline_pending
  ) {
    return null
  }

  if (nextTickAt) {
    const ms = parseUtcMs(nextTickAt)
    if (Number.isFinite(ms)) return ms
  }

  const lastMs = parseUtcMs(character.last_settled_at)
  if (!Number.isFinite(lastMs)) return null
  const tickSeconds = Math.max(1, character.idle_tick_seconds || 60)
  return lastMs + tickSeconds * 1000
}
