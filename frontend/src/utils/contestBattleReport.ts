/**
 * 将道主之争 match.report 转为 BattleReportPlayer 可用的 AutochessBattleResult。
 *
 * 棋盘约定：side0 / 小 x 在屏幕下方。本人视角须把自己翻到下方；
 * 观众保持攻方在下、守方在上，并用图例标明上下方是谁。
 */
import type { AutochessBattleResult, BattleEvent, BattleReport, BattleKind, PlaybackPolicy } from '../types/autochess'

const BOARD_SIZE = 7

export interface ContestBoardViewMeta {
  /** 棋盘上方（敌方半区）显示名 */
  topLabel: string
  /** 棋盘下方（己方半区）显示名 */
  bottomLabel: string
  /** participant = 第一人称；spectator = 观众 */
  viewRole: 'participant' | 'spectator'
  /** 是否对事件做了攻守翻转（本人是 side_b） */
  flipped: boolean
}

export interface ContestReportViewOptions {
  viewerCharacterId?: number | null
  sideACharacterId?: number | null
  sideBCharacterId?: number | null
  sideAName?: string
  sideBName?: string
  /** 后端战斗种类（挂到 AutochessBattleResult） */
  battleKind?: BattleKind
  /** 后端播控策略 */
  playbackPolicy?: PlaybackPolicy
}

function flipX(x: number): number {
  return BOARD_SIZE - 1 - x
}

function flipCoord(c: unknown): unknown {
  if (!c || typeof c !== 'object') return c
  const o = c as Record<string, unknown>
  if (typeof o.x !== 'number') return c
  return { ...o, x: flipX(o.x) }
}

/**
 * 把攻方视角事件翻成守方第一人称（side 对调 + x 轴翻转）。
 */
export function flipBattleEventsForDefender(events: BattleEvent[]): BattleEvent[] {
  return events.map((ev) => {
    const raw = ev as Record<string, unknown>
    const next: Record<string, unknown> = { ...raw }

    if (typeof raw.side === 'number') {
      next.side = 1 - raw.side
    }

    for (const key of ['from', 'to', 'cell', 'pos', 'back_to', 'target_cell'] as const) {
      if (raw[key] != null) {
        next[key] = flipCoord(raw[key])
      }
    }

    if (Array.isArray(raw.path)) {
      next.path = raw.path.map(flipCoord)
    }

    if (ev.type === 'battle_start') {
      const units = Array.isArray(raw.units) ? raw.units : []
      next.units = units.map((u) => {
        const unit = u as Record<string, unknown>
        return {
          ...unit,
          x: typeof unit.x === 'number' ? flipX(unit.x) : unit.x,
          side: typeof unit.side === 'number' ? 1 - unit.side : unit.side,
        }
      })
      const terrain = Array.isArray(raw.terrain) ? raw.terrain : []
      next.terrain = terrain.map((t) => {
        const cell = t as Record<string, unknown>
        return {
          ...cell,
          x: typeof cell.x === 'number' ? flipX(cell.x) : cell.x,
        }
      })
    }

    return next as BattleEvent
  })
}

function resolveView(
  opts?: ContestReportViewOptions,
): {
  viewerIsSideA: boolean
  viewerIsSideB: boolean
  isSpectator: boolean
  sideAName: string
  sideBName: string
} {
  const sideAName = opts?.sideAName || '甲方'
  const sideBName = opts?.sideBName || '乙方'
  const vid = opts?.viewerCharacterId
  const a = opts?.sideACharacterId
  const b = opts?.sideBCharacterId
  const viewerIsSideA = vid != null && a != null && vid === a
  const viewerIsSideB = vid != null && b != null && vid === b
  return {
    viewerIsSideA,
    viewerIsSideB,
    isSpectator: !viewerIsSideA && !viewerIsSideB,
    sideAName,
    sideBName,
  }
}

/**
 * @param raw - GET report 接口中的 report 对象
 * @param opts - 观看者与双方身份（用于第一人称翻转与图例）
 */
export function contestReportToBattleResult(
  raw: Record<string, unknown> | null | undefined,
  opts?: ContestReportViewOptions | boolean,
): AutochessBattleResult | null {
  // 兼容旧签名 contestReportToBattleResult(raw, viewerIsSideA: boolean) 已废弃
  const options: ContestReportViewOptions | undefined =
    typeof opts === 'boolean' ? undefined : opts

  if (!raw || typeof raw !== 'object') return null

  const view = resolveView(options)
  // 无身份信息时默认按攻方视角（不翻转）
  if (typeof opts === 'boolean' && !opts) {
    view.viewerIsSideA = false
    view.viewerIsSideB = true
    view.isSpectator = false
  } else if (typeof opts === 'boolean' && opts) {
    view.viewerIsSideA = true
    view.viewerIsSideB = false
    view.isSpectator = false
  }
  let base: AutochessBattleResult | null = null

  const nested = raw.autochess
  if (nested && typeof nested === 'object') {
    const a = nested as AutochessBattleResult
    if (a.report?.events?.length) {
      base = {
        ...a,
        report: { ...a.report, events: [...a.report.events] },
      }
    }
  }

  if (!base) {
    const events = (Array.isArray(raw.events) ? raw.events : []) as BattleEvent[]
    if (!events.length) return null

    let detailedLog = Array.isArray(raw.detailed_log)
      ? (raw.detailed_log as string[])
      : []
    if (!detailedLog.length) {
      detailedLog = events
        .map((ev) => String(ev.battle_text || ev.label || ''))
        .filter(Boolean)
    }

    const winnerRaw = String(raw.winner || '')
    const winner =
      winnerRaw === 'attacker' || winnerRaw === 'defender' ? winnerRaw : 'attacker'

    const report: BattleReport = {
      schema_version: Number(raw.schema_version || 1),
      seed: Number(raw.seed || 0),
      winner,
      rounds: Number(raw.rounds || 0),
      board_text: String(raw.board_text || ''),
      summary: {
        winner,
        rounds: Number(raw.rounds || 0),
        survivors: [],
        kills: [],
      },
      detailed_log: detailedLog,
      events,
    }

    const pvp = String(raw.pvp_result || '')
    const result: 'win' | 'lose' =
      pvp === 'win' || pvp === 'lose'
        ? pvp
        : winner === 'attacker'
          ? 'win'
          : 'lose'

    base = {
      mode: 'pvp',
      result,
      seed: report.seed,
      report,
      rewards: { cultivation_points: 0, spirit_stones: 0 },
      stamina: {
        left: 0,
        cap: 0,
        next_point_in_seconds: 0,
        regen_per_minute: 0,
      },
      character: {} as AutochessBattleResult['character'],
    }
  }

  // 引擎 winner / result 始终相对攻方（side_a）
  const engineWinner = base.report.winner
  const attackerWon = engineWinner === 'attacker'

  let events = base.report.events
  let result: 'win' | 'lose' = attackerWon ? 'win' : 'lose'
  let displayWinner: 'attacker' | 'defender' = engineWinner === 'defender' ? 'defender' : 'attacker'

  if (view.viewerIsSideB) {
    events = flipBattleEventsForDefender(events)
    // 翻转后「下方=原守方」视为 attacker 语义给播放器：胜负对本人取反
    result = attackerWon ? 'lose' : 'win'
    displayWinner = attackerWon ? 'defender' : 'attacker'
  } else if (view.viewerIsSideA) {
    result = attackerWon ? 'win' : 'lose'
    displayWinner = engineWinner === 'defender' ? 'defender' : 'attacker'
  } else {
    // 观众：不翻转棋盘；result 仅作色标，文案用姓名
    result = attackerWon ? 'win' : 'lose'
  }

  const meta: ContestBoardViewMeta = view.viewerIsSideB
    ? {
        topLabel: view.sideAName,
        bottomLabel: `${view.sideBName}（我）`,
        viewRole: 'participant',
        flipped: true,
      }
    : view.viewerIsSideA
      ? {
          topLabel: view.sideBName,
          bottomLabel: `${view.sideAName}（我）`,
          viewRole: 'participant',
          flipped: false,
        }
      : {
          topLabel: `上方 · ${view.sideBName}`,
          bottomLabel: `下方 · ${view.sideAName}`,
          viewRole: 'spectator',
          flipped: false,
        }

  const out: AutochessBattleResult & { board_view?: ContestBoardViewMeta } = {
    ...base,
    result,
    report: {
      ...base.report,
      winner: displayWinner,
      events,
      summary: {
        ...base.report.summary,
        winner: displayWinner,
      },
    },
    board_view: meta,
  }
  // 透传后端播控（信封在 match report / live 上，或 raw 顶层）
  const kind =
    options?.battleKind ??
    (typeof raw.battle_kind === 'string' ? (raw.battle_kind as BattleKind) : undefined)
  const policy =
    options?.playbackPolicy ??
    (raw.playback_policy && typeof raw.playback_policy === 'object'
      ? (raw.playback_policy as PlaybackPolicy)
      : undefined)
  if (kind) out.battle_kind = kind
  if (policy) out.playback_policy = policy
  return out
}

/** 从战报结果取出上下方图例 */
export function boardViewFromResult(
  report: AutochessBattleResult | null,
): ContestBoardViewMeta | null {
  if (!report) return null
  const meta = (report as AutochessBattleResult & { board_view?: ContestBoardViewMeta })
    .board_view
  return meta || null
}
