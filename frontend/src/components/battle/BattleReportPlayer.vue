<script setup lang="ts">
/**
 * 战报播放器：数据源 = 开战响应（无服务端拉取）。
 *
 * 播控以后端 ``playback_policy`` / ``battle_kind`` 为准（见 domain.battle_presentation）：
 * - exploration：简易可切，播/单步/跳过全开；
 * - dao_contest_live：强制详细，禁操作，游标跟 liveEventCursor；
 * - dao_contest_replay：默认详细，可播/单步/跳过，同战报重拉可保持终局。
 */
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import BoardGrid from '../board/BoardGrid.vue'
import type {
  BoardFx,
  BoardPiece,
  BoardTerrainCell,
} from '../board/BoardGrid.vue'
import type {
  AutochessBattleResult,
  BattleEvent,
  EventCoord,
  PlaybackPolicy,
} from '../../types/autochess'
import { DEFAULT_EXPLORATION_PLAYBACK_POLICY } from '../../types/autochess'

const props = defineProps<{
  report: AutochessBattleResult | null
  /**
   * 后端播控策略（优先）。缺省时读 ``report.playback_policy``；
   * 再缺省按探索自由回放兜底（兼容旧 sessionStorage）。
   */
  playbackPolicy?: PlaybackPolicy | null
  /**
   * 服务端已揭示的对战事件数（battle_event tick 计数）。
   * 仅当 policy.cursor_locked_to_server 时对齐。
   */
  liveEventCursor?: number | null
  /** 棋盘上方标注（观众/道主之争） */
  boardTopLabel?: string
  /** 棋盘下方标注 */
  boardBottomLabel?: string
  /**
   * @deprecated 仅兼容旧调用；有 playback_policy 时忽略。
   */
  allowSkip?: boolean
  /** @deprecated 仅兼容旧调用 */
  preferDetail?: boolean
  /** @deprecated 仅兼容旧调用；请用 playback_policy.cursor_locked_to_server */
  liveMode?: boolean
}>()

/**
 * 归一化策略；缺字段时用探索默认值填齐。
 *
 * @param raw - 后端或局部策略
 */
function normalizePolicy(raw: Partial<PlaybackPolicy> | null | undefined): PlaybackPolicy {
  const base = DEFAULT_EXPLORATION_PLAYBACK_POLICY
  if (!raw) return { ...base }
  return {
    allow_simple_mode: raw.allow_simple_mode ?? base.allow_simple_mode,
    default_detail: raw.default_detail ?? base.default_detail,
    allow_play_pause: raw.allow_play_pause ?? base.allow_play_pause,
    allow_step: raw.allow_step ?? base.allow_step,
    allow_skip: raw.allow_skip ?? base.allow_skip,
    cursor_locked_to_server: raw.cursor_locked_to_server ?? base.cursor_locked_to_server,
    hold_final_on_reload: raw.hold_final_on_reload ?? base.hold_final_on_reload,
  }
}

/**
 * 解析生效播控：prop > report.playback_policy > 旧 props 映射 > 探索默认。
 */
const policy = computed<PlaybackPolicy>(() => {
  if (props.playbackPolicy) return normalizePolicy(props.playbackPolicy)
  if (props.report?.playback_policy) return normalizePolicy(props.report.playback_policy)
  // 旧调用兼容（赛会页尚未改完 / 内存旧对象）
  if (props.liveMode) {
    return normalizePolicy({
      allow_simple_mode: false,
      default_detail: true,
      allow_play_pause: false,
      allow_step: false,
      allow_skip: false,
      cursor_locked_to_server: true,
      hold_final_on_reload: false,
    })
  }
  if (props.preferDetail) {
    return normalizePolicy({
      ...DEFAULT_EXPLORATION_PLAYBACK_POLICY,
      default_detail: true,
      hold_final_on_reload: true,
      allow_skip: props.allowSkip !== false,
    })
  }
  return normalizePolicy({
    ...DEFAULT_EXPLORATION_PLAYBACK_POLICY,
    allow_skip: props.allowSkip !== false,
  })
})

/** 播放游标（已消费的事件数；board 与日志都由它派生） */
const evCursor = ref(0)
const playing = ref(false)
const detailMode = ref(Boolean(policy.value.default_detail || policy.value.cursor_locked_to_server))
const logBoxRef = ref<HTMLElement | null>(null)
/**
 * 同战报身份（勿只用 seed：多场 seed=0 会误判为同战）。
 */
const lastReportIdentity = ref<string | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

/** 游标锁定 = 直播演出（后端 policy） */
const isLive = computed(() => policy.value.cursor_locked_to_server)
/** 是否允许简易/详细切换 */
const allowSimpleMode = computed(() => policy.value.allow_simple_mode && !isLive.value)
/** 播放/暂停/重播区 */
const canControl = computed(() => policy.value.allow_play_pause && !isLive.value)

/**
 * 生成战报身份键：seed 常撞车，叠加事件数/回合/胜方/日志行数区分场次。
 *
 * @param report - 开战响应；空则 null
 */
function reportIdentity(report: AutochessBattleResult | null): string | null {
  if (!report?.report) return null
  const r = report.report
  const eventCount = Array.isArray(r.events) ? r.events.length : 0
  const logCount = Array.isArray(r.detailed_log) ? r.detailed_log.length : 0
  const firstType = eventCount > 0 ? String(r.events[0]?.type ?? '') : ''
  const lastType = eventCount > 0 ? String(r.events[eventCount - 1]?.type ?? '') : ''
  return [
    report.seed ?? r.seed ?? 0,
    eventCount,
    r.rounds ?? 0,
    r.winner ?? '',
    logCount,
    firstType,
    lastType,
  ].join('|')
}


const boardLegend = computed(() => {
  const top = props.boardTopLabel
  const bottom = props.boardBottomLabel
  if (!top && !bottom) return null
  return { top: top || '上方', bottom: bottom || '下方' }
})

/** 结果中文：优先用姓名图例语境 */
const winnerText = computed(() => {
  if (!props.report) return ''
  if (props.boardBottomLabel && props.boardTopLabel) {
    // 翻转后 report.winner：attacker=下方 / defender=上方
    return props.report.report.winner === 'attacker'
      ? `${props.boardBottomLabel} 胜`
      : `${props.boardTopLabel} 胜`
  }
  return props.report.report.winner === 'attacker' ? '进攻方胜' : '防守方胜'
})

/** 自动步进间隔 */
function playbackMs(): number {
  const raw = import.meta.env.VITE_BATTLE_PLAYBACK_MS
  const parsed = raw ? Number(raw) : 400
  return Number.isFinite(parsed) && parsed >= 50 ? parsed : 400
}

const events = computed<BattleEvent[]>(() => {
  const raw = props.report?.report?.events
  return Array.isArray(raw) ? raw : []
})
const lines = computed(() => {
  const raw = props.report?.report?.detailed_log
  return Array.isArray(raw) ? raw : []
})

/**
 * 单个事件对应的日志行数（镜像后端 battle_text.render_detailed 的规则）。
 */
const ONE_LINE_TYPES = new Set([
  'round_start',
  'initiative',
  'move',
  'hit_check',
  'damage',
  'obstacle_hit',
  'abyss_pass',
  'abyss_bounce',
  'blocked',
  'death',
  'battle_end',
  'taunt',
  'ai_retarget',
])

function linesOfEvent(ev: BattleEvent): number {
  if (ev.type === 'battlefield_layer') {
    const coverage = ev.coverage
    return coverage == null || coverage === 'none' ? 0 : 1
  }
  return ONE_LINE_TYPES.has(ev.type) ? 1 : 0
}

/** 已消费事件对应的可见日志行数 */
const lineCount = computed(() => {
  let total = 0
  const list = events.value
  const limit = Math.min(evCursor.value, list.length)
  for (let i = 0; i < limit; i += 1) total += linesOfEvent(list[i])
  return total
})

const visibleLines = computed(() => lines.value.slice(0, lineCount.value))
/** 无事件时不算「播完」，避免 0>=0 把控件逻辑搅乱 */
const finished = computed(() => {
  const total = events.value.length
  return total > 0 && evCursor.value >= total
})
/**
 * 单步 / 跳过：以后端 policy 为准；播完不禁用（单步=回开局；跳过=停终局）。
 */
const canStep = computed(
  () =>
    policy.value.allow_step &&
    detailMode.value &&
    !isLive.value &&
    events.value.length > 0,
)
const canSkipAnim = computed(
  () =>
    policy.value.allow_skip &&
    detailMode.value &&
    !isLive.value &&
    events.value.length > 0,
)
/** 简易档展示全部日志（不跟播放游标） */
const simpleLogLines = computed(() => lines.value)

/** 棋盘回放状态（重放事件流；事件量级小，直接全量重算） */
interface ReplayState {
  pieces: BoardPiece[]
  terrain: BoardTerrainCell[]
  round: number
}

function replayEvents(count: number): ReplayState {
  interface PieceTrack extends BoardPiece {
    alive: boolean
  }
  const pieceMap = new Map<string, PieceTrack>()
  const terrainMap = new Map<string, BoardTerrainCell>()
  const bounceBack = new Map<string, { x: number; y: number }>()
  let round = 0

  const list = events.value
  const limit = Math.min(count, list.length)
  for (let i = 0; i < limit; i += 1) {
    const ev = list[i]
    switch (ev.type) {
      case 'battle_start': {
        const units = (ev.units ?? []) as {
          uid: string
          kind: string
          side: number
          name: string
          x: number
          y: number
          hp: number
        }[]
        for (const unit of units) {
          pieceMap.set(unit.uid, {
            uid: unit.uid,
            x: unit.x,
            y: unit.y,
            kind: unit.kind,
            side: unit.side,
            label: pieceLabel(unit.kind, unit.side, unit.name),
            hp: unit.hp,
            max_hp: unit.hp,
            alive: true,
          })
        }
        const cells = (ev.terrain ?? []) as BoardTerrainCell[]
        for (const cell of cells) {
          terrainMap.set(`${cell.x},${cell.y}`, cell)
        }
        break
      }
      case 'round_start':
        round = Number(ev.round ?? round)
        break
      case 'abyss_bounce': {
        const back = ev.back_to as { x: number; y: number } | undefined
        if (back) bounceBack.set(String(ev.uid), back)
        break
      }
      case 'move': {
        const piece = pieceMap.get(String(ev.uid))
        if (!piece) break
        const path = (ev.path ?? []) as { x: number; y: number }[]
        let dest = path.length ? path[path.length - 1] : { x: piece.x, y: piece.y }
        if (ev.stop_reason === 'abyss_bounce') {
          dest = bounceBack.get(String(ev.uid)) ?? dest
        }
        piece.x = dest.x
        piece.y = dest.y
        break
      }
      case 'damage': {
        const piece = pieceMap.get(String(ev.target))
        if (piece) piece.hp = Number(ev.hp_after ?? piece.hp)
        break
      }
      case 'death': {
        const piece = pieceMap.get(String(ev.uid))
        if (piece) piece.alive = false
        break
      }
      case 'obstacle_hit': {
        const cell = ev.cell as { x: number; y: number } | undefined
        if (ev.result === 'break' && cell) {
          terrainMap.delete(`${cell.x},${cell.y}`)
        }
        break
      }
      default:
        break
    }
  }

  return {
    pieces: [...pieceMap.values()].filter((piece) => piece.alive),
    terrain: [...terrainMap.values()],
    round,
  }
}

/** 棋子标签：己方按种类，敌方除傀宠化外统一「敌」 */
function pieceLabel(kind: string, side: number, name: string): string {
  const KIND_LABELS: Record<string, string> = {
    main: '本',
    puppet: '傀',
    pet: '宠',
    avatar: '化',
    prop: '器',
  }
  if (side === 1) {
    return kind === 'main' ? '敌' : (KIND_LABELS[kind] ?? '敌')
  }
  return KIND_LABELS[kind] ?? (name ? name.charAt(0) : '?')
}

/** 简易档展示开局站位；详细档跟随播放游标；播完后保持终局（不复位） */
const boardState = computed<ReplayState>(() => {
  if (isLive.value || detailMode.value || finished.value) {
    // 游标 0 时也至少播到 battle_start（1），避免空白棋盘
    return replayEvents(Math.max(1, evCursor.value))
  }
  return replayEvents(1)
})

/** 当前刚消费的事件（驱动棋盘演出高亮） */
const currentEvent = computed<BattleEvent | null>(() => {
  const list = events.value
  if (evCursor.value <= 0 || list.length === 0) return null
  return list[Math.min(evCursor.value, list.length) - 1] ?? null
})

function asCoord(raw: unknown): EventCoord | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  if (typeof o.x !== 'number' || typeof o.y !== 'number') return null
  return { x: o.x, y: o.y }
}

/**
 * 根据当前事件生成棋盘演出：路径高亮、行动/攻击浮标、攻击连线、棋子高亮。
 */
const boardPresentation = computed(() => {
  const base = boardState.value
  const ev = currentEvent.value
  const pieceByUid = new Map(base.pieces.map((p) => [p.uid, p]))
  const fx: BoardFx = { cells: [], tags: [], beam: null }
  const highlight = new Map<string, NonNullable<BoardPiece['highlight']>>()

  if (!ev || finished.value) {
    return {
      pieces: base.pieces,
      terrain: base.terrain,
      round: base.round,
      fx: null as BoardFx | null,
    }
  }

  const mark = (uid: string | undefined, kind: NonNullable<BoardPiece['highlight']>) => {
    if (!uid) return
    highlight.set(uid, kind)
  }

  if (ev.type === 'initiative') {
    // 先攻仅高亮行动者，不播移动/攻击动画；下一条才是该单位行动
    const uid = String(ev.uid || '')
    mark(uid, 'actor')
    const piece = pieceByUid.get(uid)
    if (piece) {
      fx.tags!.push({ x: piece.x, y: piece.y, text: '先攻', tone: 'act' })
    }
  } else if (ev.type === 'taunt' || ev.type === 'ai_retarget') {
    const uid = String(ev.uid || '')
    mark(uid, 'actor')
    const piece = pieceByUid.get(uid)
    if (piece) {
      fx.tags!.push({ x: piece.x, y: piece.y, text: '行动', tone: 'act' })
    }
  } else if (ev.type === 'move') {
    const uid = String(ev.uid || '')
    mark(uid, 'actor')
    const path = (ev.path ?? []) as EventCoord[]
    if (path.length) {
      const from = path[0]
      const to = path[path.length - 1]
      fx.cells!.push({ x: from.x, y: from.y, tone: 'from' })
      for (let i = 1; i < path.length - 1; i += 1) {
        fx.cells!.push({ x: path[i].x, y: path[i].y, tone: 'path' })
      }
      fx.cells!.push({ x: to.x, y: to.y, tone: 'to' })
      fx.tags!.push({
        x: to.x,
        y: to.y,
        text: `移→(${to.x},${to.y})`,
        tone: 'move',
      })
      if (path.length >= 2) {
        fx.beam = {
          fromX: from.x,
          fromY: from.y,
          toX: to.x,
          toY: to.y,
          tone: 'move',
        }
      }
    }
  } else if (ev.type === 'hit_check' || ev.type === 'damage') {
    const attacker = String(ev.attacker || '')
    const target = String(ev.target || '')
    mark(attacker, 'actor')
    mark(target, ev.type === 'damage' ? 'hit' : 'target')
    const a = pieceByUid.get(attacker)
    const t = pieceByUid.get(target)
    if (t) {
      fx.cells!.push({ x: t.x, y: t.y, tone: 'target' })
    }
    if (a && t) {
      fx.beam = {
        fromX: a.x,
        fromY: a.y,
        toX: t.x,
        toY: t.y,
        tone: 'attack',
      }
    }
    if (ev.type === 'hit_check') {
      const hit = Boolean(ev.hit)
      const tagPiece = t || a
      if (tagPiece) {
        fx.tags!.push({
          x: tagPiece.x,
          y: tagPiece.y,
          text: hit ? '攻击' : '未中',
          tone: hit ? 'atk' : 'miss',
        })
      }
    } else {
      const dmg = Number(ev.final ?? 0)
      if (t) {
        fx.tags!.push({
          x: t.x,
          y: t.y,
          text: dmg > 0 ? `-${dmg}` : '0',
          tone: 'hit',
        })
      }
    }
  } else if (ev.type === 'death') {
    const uid = String(ev.uid || '')
    // 阵亡单位已从 pieces 过滤；尽量标在上一格（用事件前状态较难，标 actor 附近）
    // 用 replay 到 cursor-1 取死亡前位置
    const before = replayEvents(Math.max(0, evCursor.value - 1))
    const ghost = before.pieces.find((p) => p.uid === uid)
    if (ghost) {
      fx.cells!.push({ x: ghost.x, y: ghost.y, tone: 'target' })
      fx.tags!.push({ x: ghost.x, y: ghost.y, text: '阵亡', tone: 'death' })
    }
  } else if (ev.type === 'obstacle_hit') {
    const cell = asCoord(ev.cell)
    const uid = String(ev.uid || '')
    mark(uid, 'actor')
    if (cell) {
      fx.cells!.push({ x: cell.x, y: cell.y, tone: 'to' })
      fx.tags!.push({
        x: cell.x,
        y: cell.y,
        text: ev.result === 'break' ? '破障' : '撞障',
        tone: 'move',
      })
    }
  }

  const pieces: BoardPiece[] = base.pieces.map((p) => ({
    ...p,
    highlight: highlight.get(p.uid) ?? null,
  }))

  return {
    pieces,
    terrain: base.terrain,
    round: base.round,
    fx: (fx.cells!.length || fx.tags!.length || fx.beam) ? fx : null,
  }
})

/** 四象结算一行 */
const layerLine = computed(() => {
  const parts: string[] = []
  for (const ev of events.value) {
    if (ev.type !== 'battlefield_layer') continue
    const name =
      (ev.layer_label_zh as string | undefined) ||
      ({ environment: '环境', weather: '天气', effect: '场上效果' } as Record<string, string>)[
        String(ev.layer)
      ] ||
      String(ev.layer)
    let resolved: string
    if (ev.coverage === 'split') {
      resolved = '平局分区'
    } else if (ev.coverage === 'cancelled') {
      resolved = '互抵为无'
    } else if (ev.coverage === 'none' || ev.coverage == null) {
      resolved = '无'
    } else {
      const zh = ev.resolved_full_label_zh as string | undefined
      const raw = ev.resolved_full as string | null
      resolved = zh || (raw ? `未知(${raw})` : '无')
    }
    const notes = (ev.combat_notes as string[] | undefined) || []
    if (notes.length) resolved = `${resolved}（${notes.join('；')}）`
    parts.push(`${name}：${resolved}`)
  }
  return parts.join(' · ')
})

function stopTimer(): void {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  playing.value = false
}

/**
 * 统计前 cursor 个事件对应的日志行数（不依赖 computed，避免 while 里读到陈旧值）。
 *
 * @param cursor - 已消费事件数
 */
function countLogLines(cursor: number): number {
  let total = 0
  const list = events.value
  const limit = Math.min(cursor, list.length)
  for (let i = 0; i < limit; i += 1) total += linesOfEvent(list[i])
  return total
}

/**
 * 推进事件游标：优先走到「新增一行日志」；若后续事件都不产日志则每次只 +1，避免一次跳到终局。
 */
function advanceOneLine(): void {
  const list = events.value
  if (evCursor.value >= list.length) return
  const before = countLogLines(evCursor.value)
  const start = evCursor.value
  while (evCursor.value < list.length) {
    evCursor.value += 1
    if (countLogLines(evCursor.value) > before) return
  }
  // 剩余事件均无日志行：回退为单事件步进，防止一帧播完
  if (countLogLines(evCursor.value) <= before && start < list.length) {
    evCursor.value = Math.min(start + 1, list.length)
  }
}

/** 自动播放 / 暂停切换（直播中禁用）。 */
function togglePlay(): void {
  if (isLive.value) return
  if (playing.value) {
    stopTimer()
    return
  }
  // 重播：从开局再播；播完保持终局，点「重播」才复位
  if (finished.value) evCursor.value = Math.min(1, Math.max(events.value.length, 0))
  if (events.value.length <= 0) return
  // 已在终局且 length>=1 时，上面把游标置 1；若 length==0 则直接返回
  if (evCursor.value >= events.value.length) evCursor.value = 1
  playing.value = true
  timer = setInterval(() => {
    if (evCursor.value < events.value.length) {
      advanceOneLine()
    } else {
      stopTimer()
      // 停在终局棋盘
      evCursor.value = events.value.length
    }
  }, playbackMs())
}

/** 单步前进（按棋盘事件 +1；已在终局则回到开局再看）。 */
function stepOnce(): void {
  if (!canStep.value) return
  stopTimer()
  const total = events.value.length
  if (total <= 0) return
  // 终局再点单步：复位到开局站位，便于继续逐步看
  if (evCursor.value >= total) {
    evCursor.value = 1
    return
  }
  evCursor.value += 1
}

/** 跳过动画：直接到终局（已在终局则保持）。 */
function skipToEnd(): void {
  if (!canSkipAnim.value) return
  stopTimer()
  if (events.value.length <= 0) return
  evCursor.value = events.value.length
}

/**
 * 按服务端直播游标对齐（中途观战不从头播）。
 * battle_event_cursor = 已揭示事件数；棋盘游标取 max(1, cursor)。
 */
function applyLiveCursor(cursor: number | null | undefined): void {
  if (!isLive.value || !props.report) return
  stopTimer()
  detailMode.value = true
  const total = events.value.length
  if (total <= 0) {
    evCursor.value = 0
    return
  }
  const target = Math.max(1, Math.min(total, Number(cursor || 0)))
  evCursor.value = target
  playing.value = false
}

/**
 * 进入详细回放：停在开局（可立刻单步/跳过/播放）。
 * 默认不自动播完——自动播完后按钮会变灰，只剩「重播」可点。
 *
 * @param opts.autoplay - 为 true 时从开局自动播放（仅调用方显式需要时）
 */
function startDetailPlayback(opts?: { autoplay?: boolean }): void {
  if (isLive.value) return
  stopTimer()
  if (!props.report || events.value.length <= 0) {
    evCursor.value = 0
    return
  }
  // 至少消费 battle_start，棋盘有开局站位
  evCursor.value = 1
  if (opts?.autoplay) {
    togglePlay()
  }
}

watch(
  () => props.report,
  (report) => {
    stopTimer()
    // 按后端策略：默认详细或游标锁定时强制详细
    if (policy.value.default_detail || policy.value.cursor_locked_to_server) {
      detailMode.value = true
    }
    if (!report) {
      evCursor.value = 0
      lastReportIdentity.value = null
      return
    }
    const identity = reportIdentity(report)
    if (policy.value.cursor_locked_to_server) {
      applyLiveCursor(props.liveEventCursor)
      lastReportIdentity.value = identity
      return
    }
    const sameBattle =
      identity != null &&
      lastReportIdentity.value != null &&
      lastReportIdentity.value === identity
    lastReportIdentity.value = identity

    // 「同战报保持终局」仅当后端 hold_final_on_reload（赛会回放）
    const contestReplayHold =
      policy.value.hold_final_on_reload &&
      sameBattle &&
      detailMode.value &&
      events.value.length > 0

    if (contestReplayHold && evCursor.value >= events.value.length) {
      evCursor.value = events.value.length
      return
    }
    if (contestReplayHold && evCursor.value > 1) {
      return
    }
    // 简易：不推进游标；详细：停在开局，等用户播/单步/跳过
    if (detailMode.value) {
      startDetailPlayback({ autoplay: false })
    } else {
      evCursor.value = 0
    }
  },
  { immediate: true },
)

watch(
  () => [policy.value.cursor_locked_to_server, props.liveEventCursor] as const,
  ([locked]) => {
    if (locked) applyLiveCursor(props.liveEventCursor)
  },
)

watch(
  () => policy.value.cursor_locked_to_server,
  (locked, wasLocked) => {
    // 直播结束（策略从锁定→解锁）：停在结局，可重播
    if (wasLocked && !locked && props.report) {
      detailMode.value = true
      evCursor.value = events.value.length
      playing.value = false
    }
  },
)

/** 切到详细档：停在开局（不自动播完）；切回简易停止动画 */
watch(detailMode, (detail, wasDetail) => {
  if (isLive.value || !props.report) return
  if (detail && !wasDetail) {
    startDetailPlayback({ autoplay: false })
  } else if (!detail && wasDetail) {
    stopTimer()
    evCursor.value = 0
  }
})

watch(lineCount, async () => {
  await nextTick()
  if (!detailMode.value) return
  const el = logBoxRef.value
  if (el) el.scrollTop = el.scrollHeight
})

onUnmounted(stopTimer)
</script>

<template>
  <el-card v-if="report" shadow="never">
    <template #header>
      <div class="player-header">
        <el-text tag="b">{{ isLive ? '对战直播' : '战报回放' }}</el-text>
        <el-tag :type="report.result === 'win' ? 'success' : 'danger'" size="small">
          {{ winnerText }}（{{ report.report.rounds }} 回合）
        </el-tag>
        <el-tag v-if="detailMode && boardPresentation.round > 0" size="small" type="info">
          第 {{ boardPresentation.round }} 回合
        </el-tag>
        <el-tag v-if="isLive" type="danger" size="small">全服同步 · 不可操作</el-tag>
        <el-text v-if="detailMode && !isLive" type="info" size="small">
          演算种子 {{ report.seed }}
        </el-text>
        <el-switch
          v-if="allowSimpleMode"
          v-model="detailMode"
          size="small"
          active-text="详细"
          inactive-text="简易"
          class="player-switch"
        />
      </div>
    </template>

    <!-- 简易：无棋盘，结果 + 全文日志 -->
    <div v-if="!detailMode && allowSimpleMode" class="simple-body">
      <el-descriptions :column="2" size="small" border class="summary-box">
        <el-descriptions-item label="胜方">{{ winnerText }}</el-descriptions-item>
        <el-descriptions-item label="回合数">{{ report.report.rounds }}</el-descriptions-item>
        <el-descriptions-item label="击杀">
          {{ report.report.summary.kills.length ? report.report.summary.kills.join('、') : '无' }}
        </el-descriptions-item>
        <el-descriptions-item label="奖励">
          修为 +{{ report.rewards.cultivation_points }} · 灵石 +{{ report.rewards.spirit_stones }}
        </el-descriptions-item>
      </el-descriptions>
      <el-text v-if="layerLine" type="info" size="small" class="layer-line">
        {{ layerLine }}
      </el-text>
      <div ref="logBoxRef" class="log-box simple-log">
        <p v-for="(line, index) in simpleLogLines" :key="index" class="log-line">
          {{ line }}
        </p>
        <el-text v-if="!simpleLogLines.length" type="info" size="small">暂无详细日志</el-text>
      </div>
      <el-text type="info" size="small">
        简易模式仅展示结果与日志；切到「详细」可看棋盘，再用播放/单步/跳过推进。
      </el-text>
    </div>

    <!-- 详细 / 直播：棋盘 + 同步日志 -->
    <div v-else class="player-body">
      <div class="board-pane">
        <div v-if="boardLegend" class="board-legend top">{{ boardLegend.top }}</div>
        <BoardGrid
          :terrain="boardPresentation.terrain"
          :pieces="boardPresentation.pieces"
          :fx="boardPresentation.fx"
        />
        <div v-if="boardLegend" class="board-legend bottom">{{ boardLegend.bottom }}</div>
        <el-text v-if="layerLine" type="info" size="small" class="layer-line">
          {{ layerLine }}
        </el-text>
        <el-text
          v-if="finished && !isLive"
          type="success"
          size="small"
          class="final-hint"
        >
          已停在终局站位（点「重播」可从头观看）
        </el-text>
      </div>

      <div class="side-pane">
        <div v-if="canControl" class="player-controls">
          <el-button size="small" @click="togglePlay">
            {{ playing ? '暂停' : finished ? '重播' : '播放' }}
          </el-button>
          <el-button
            v-if="policy.allow_step"
            size="small"
            :disabled="!canStep"
            @click="stepOnce"
          >
            单步
          </el-button>
          <el-button
            v-if="policy.allow_skip"
            size="small"
            :disabled="!canSkipAnim"
            @click="skipToEnd"
          >
            跳过动画
          </el-button>
          <el-text v-if="events.length === 0" type="warning" size="small">
            本战报无结构化事件，无法单步/跳过（仅日志）
          </el-text>
          <el-text v-else type="info" size="small">
            {{ lineCount }}/{{ lines.length }} 行 · 事件 {{ evCursor }}/{{ events.length }}
          </el-text>
        </div>
        <el-text v-else type="warning" size="small" class="live-hint">
          直播演出中 · 棋盘与全服同步推进，结束后可重播
        </el-text>
        <div ref="logBoxRef" class="log-box">
          <p v-for="(line, index) in visibleLines" :key="index" class="log-line">
            {{ line }}
          </p>
          <el-text v-if="finished && lines.length && !isLive" type="success" size="small">
            —— 回放结束 ——
          </el-text>
        </div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.player-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.player-switch {
  margin-left: auto;
}

.player-body {
  display: grid;
  grid-template-columns: minmax(280px, 400px) 1fr;
  gap: 1rem;
  align-items: start;
}

.simple-body {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.simple-log {
  height: max(280px, calc(100vh - 380px));
}

.board-pane {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
}

.board-legend {
  font-size: 0.8rem;
  color: var(--el-text-color-regular);
  padding: 0.15rem 0.35rem;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}

.board-legend.top {
  border-left: 3px solid var(--el-color-danger);
}

.board-legend.bottom {
  border-left: 3px solid var(--el-color-primary);
}

.live-hint {
  display: block;
  margin-bottom: 0.35rem;
}

.layer-line {
  line-height: 1.4;
}

.final-hint {
  line-height: 1.35;
}

.side-pane {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 0;
}

.summary-box {
  margin-bottom: 0.25rem;
}

.player-controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.log-box {
  height: max(240px, calc(100vh - 340px));
  overflow-y: auto;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  padding: 0.5rem 0.75rem;
}

.log-line {
  margin: 0 0 0.25rem;
  font-size: 13px;
  line-height: 1.5;
}

@media (max-width: 800px) {
  .player-body {
    grid-template-columns: 1fr;
  }

  .log-box {
    height: max(220px, calc(100vh - 560px));
  }
}
</style>
