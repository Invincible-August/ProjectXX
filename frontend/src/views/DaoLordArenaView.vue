<script setup lang="ts">
/**
 * 道主之争擂台页：分组对战表、棋盘直播/回放、整备改阵入口。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import BattleReportPlayer from '../components/battle/BattleReportPlayer.vue'
import DaoContestBracketBoard from '../components/daoLord/DaoContestBracketBoard.vue'
import { useDaoLordStore } from '../stores/daoLord'
import { useWsStore } from '../stores/ws'
import type { DaoContestMatchPublic } from '../types/daoLord'
import type { AutochessBattleResult, PlaybackPolicy } from '../types/autochess'
import { DEFAULT_EXPLORATION_PLAYBACK_POLICY } from '../types/autochess'
import {
  boardViewFromResult,
  contestReportToBattleResult,
} from '../utils/contestBattleReport'
import { useSyncedCountdown } from '../composables/useSyncedCountdown'

const router = useRouter()
const daoLordStore = useDaoLordStore()
const wsStore = useWsStore()

const busy = ref(false)
const liveOpen = ref(false)
const watchingMatchId = ref<number | null>(null)
const boardReport = ref<AutochessBattleResult | null>(null)
/** 主动点「离开」时跳过路由守卫重复判负提示 */
const intentionalLeave = ref(false)
/**
 * 用户主动关掉的直播场次：关后不再强制弹窗；点对阵表可再打开。
 * 关窗 ≠ 离场判负，赛程仍按服务端播报时钟走完。
 */
const dismissedLiveMatchIds = ref<Set<number>>(new Set())
let pollTimer: ReturnType<typeof setInterval> | null = null
let liveTimer: ReturnType<typeof setInterval> | null = null

const arena = computed(() => daoLordStore.arena)
const matches = computed(() => arena.value?.bracket?.matches || [])
const live = computed(() => daoLordStore.liveState)
const meCharacterId = computed(() => arena.value?.me_character_id ?? null)

const boardView = computed(() => boardViewFromResult(boardReport.value))

const phaseEndsAt = computed(() => arena.value?.phase_ends_at ?? null)
const serverNow = computed(() => arena.value?.server_now ?? null)
const syncedCountdown = useSyncedCountdown(phaseEndsAt, serverNow)

const livePrepEndsAt = computed(() => live.value?.prep_ends_at ?? null)
const liveServerNow = computed(() => live.value?.server_now ?? null)
const livePrepCountdown = useSyncedCountdown(livePrepEndsAt, liveServerNow)

const liveEventCursor = computed(() => live.value?.battle_event_cursor ?? 0)

/**
 * 播控策略：优先直播态，其次 match report，再次战报信封；缺省探索兜底。
 * 不再使用 allowSkip/liveMode 等旧 props。
 */
const boardPlaybackPolicy = computed<PlaybackPolicy>(() => {
  const fromLive = live.value?.playback_policy
  if (fromLive) return fromLive
  const fromMatch = daoLordStore.matchReport?.playback_policy
  if (fromMatch) return fromMatch
  return boardReport.value?.playback_policy ?? DEFAULT_EXPLORATION_PLAYBACK_POLICY
})

/**
 * 晋级表高亮：优先本人 active 场，否则本道整备/直播场次。
 */
const highlightMatchIdList = computed(() => {
  const mine = arena.value?.my_active_match?.id
  if (mine != null) return [mine]
  return (
    arena.value?.my_dao_active_match_ids ||
    arena.value?.active_match_ids ||
    []
  )
})

/** 改阵提示：合并为单条 banner，避免与 phase Tag 重复堆叠 */
const loadoutHint = computed(() => {
  if (!arena.value?.can_adjust_loadout) return null
  const p = arena.value.phase
  if (p === 'rsvp') {
    return '入席确认中，可调整上阵、阵法、功法与装备（倒计时结束前）。'
  }
  if (p === 'round_countdown') {
    return '开赛倒计时中，仍可调整上阵、阵法、功法与装备（倒计时结束前）。'
  }
  if (p === 'round_gap') {
    return '轮间休息，可调整上阵、阵法、功法与装备（倒计时结束前）。'
  }
  if (p === 'adjust') {
    return '整备倒计时内可改阵；倒计时结束将锁阵并开战。完成后点布阵页「回擂台」返回。'
  }
  return '可调整上阵、阵法、功法与装备（倒计时结束前）。'
})

/** 本人有直播场次但已关窗：提示可点对阵回看 */
const liveDismissedHint = computed(() => {
  const m = arena.value?.my_active_match
  if (!m || liveOpen.value) return null
  if (!(m.live_active || m.status === 'playing')) return null
  if (!dismissedLiveMatchIds.value.has(m.id)) return null
  const a = m.side_a?.name || '甲方'
  const b = m.side_b?.name || '乙方'
  return `本场演出进行中（${a} vs ${b}）。可关闭不看，须等播报结束；点对阵表或「回到播报」可再看。`
})

const phaseLabel = computed(() => {
  const p = arena.value?.phase
  // 顶部 Tag 仅显示阶段名；改阵说明见 loadoutHint，避免重复堆叠
  if (p === 'rsvp') return '入席确认'
  if (p === 'round_countdown') return '开赛倒计时'
  if (p === 'round_gap') return '轮间休息'
  if (p === 'adjust') return '整备'
  if (p === 'playing') return '对战演出'
  if (p === 'idle') return '已收口'
  return p || '—'
})

/**
 * 仅「正在演出/整备」的本人场次才可能离场判负。
 * 勿用 live_active alone：已 finished 但直播窗未结束时会误报判负。
 */
const canLeaveForfeit = computed(() => {
  const status = arena.value?.status
  if (status === 'settled' || status === 'cancelled' || status === 'registration') {
    return false
  }
  const m = arena.value?.my_active_match
  const me = arena.value?.me_character_id
  if (!m || me == null) return false
  if (m.status !== 'playing' && m.status !== 'adjusting') return false
  return (
    m.side_a?.character_id === me || m.side_b?.character_id === me
  )
})

const drawerTitle = computed(() => {
  if (live.value?.live_active) {
    if (live.value.phase === 'prep') return '入席准备（直播）'
    return '对战直播（棋盘演出）'
  }
  return '战报回放'
})

const showBoardPlayer = computed(() => {
  if (!boardReport.value) return false
  if (live.value?.live_active && live.value.phase === 'prep') return false
  return true
})

function stopTimers(): void {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  if (liveTimer) {
    clearInterval(liveTimer)
    liveTimer = null
  }
}

function stopLivePoll(): void {
  if (liveTimer) {
    clearInterval(liveTimer)
    liveTimer = null
  }
}

async function hydrateBoardFromReport(matchId: number): Promise<void> {
  const err = await daoLordStore.loadMatchReport(matchId)
  if (err) {
    boardReport.value = null
    return
  }
  const payload = daoLordStore.matchReport
  const match = payload?.match
  boardReport.value = contestReportToBattleResult(
    payload?.report as Record<string, unknown> | undefined,
    {
      viewerCharacterId: meCharacterId.value,
      sideACharacterId: match?.side_a?.character_id,
      sideBCharacterId: match?.side_b?.character_id,
      sideAName: match?.side_a?.name,
      sideBName: match?.side_b?.name,
      battleKind: payload?.battle_kind,
      playbackPolicy: payload?.playback_policy,
    },
  )
}

async function refresh(): Promise<void> {
  await daoLordStore.refreshArena()
  const active = daoLordStore.arena?.my_active_match
  // 仅「真正直播中」才自动开播报窗；整备中不弹（否则空战报抽屉）
  if (active && active.live_active && active.status === 'playing') {
    if (
      !dismissedLiveMatchIds.value.has(active.id) &&
      !liveOpen.value &&
      watchingMatchId.value !== active.id
    ) {
      await openLive(active.id, { auto: true })
    }
  }
}

function startLivePoll(matchId: number): void {
  stopLivePoll()
  watchingMatchId.value = matchId
  liveTimer = setInterval(async () => {
    if (watchingMatchId.value == null) return
    // 用户已关窗且本场在 dismiss 列表：停止轮询
    if (!liveOpen.value && dismissedLiveMatchIds.value.has(matchId)) {
      stopLivePoll()
      return
    }
    await daoLordStore.pollLive(watchingMatchId.value)
    const state = daoLordStore.liveState
    if (state?.phase === 'battle' && !boardReport.value) {
      await hydrateBoardFromReport(matchId)
    }
    // 自动打开：未 dismiss 且处于 prep 或已有棋盘
    if (
      !liveOpen.value &&
      !dismissedLiveMatchIds.value.has(matchId) &&
      state?.live_active &&
      (state.phase === 'prep' || boardReport.value)
    ) {
      liveOpen.value = true
    }
    if (state && !state.live_active && state.phase !== 'prep') {
      stopLivePoll()
      await hydrateBoardFromReport(matchId)
      const cleared = new Set(dismissedLiveMatchIds.value)
      cleared.delete(matchId)
      dismissedLiveMatchIds.value = cleared
      await refresh()
    }
  }, 500)
}

/**
 * @param opts.auto - 自动打开（pendingLive / refresh）
 * @param opts.fromUser - 用户点击对阵/回到播报
 */
async function openLive(
  matchId: number,
  opts?: { auto?: boolean; fromUser?: boolean },
): Promise<void> {
  if (opts?.auto && dismissedLiveMatchIds.value.has(matchId)) {
    return
  }
  if (opts?.fromUser) {
    const next = new Set(dismissedLiveMatchIds.value)
    next.delete(matchId)
    dismissedLiveMatchIds.value = next
  }
  watchingMatchId.value = matchId
  boardReport.value = null
  await daoLordStore.spectateMatch(matchId)
  await daoLordStore.pollLive(matchId)
  const state = daoLordStore.liveState
  // 区分 prep/battle：无 replay/战报时不强开空抽屉
  const isPrep = Boolean(state?.live_active && state?.phase === 'prep')
  const isBattle = Boolean(
    state?.live_active && (state?.phase === 'battle' || state?.phase === 'playing'),
  )
  if (isPrep) {
    liveOpen.value = true
    startLivePoll(matchId)
    return
  }
  if (isBattle) {
    await hydrateBoardFromReport(matchId)
    if (!boardReport.value) {
      // 战报尚未就绪：轮询等待，不弹空窗
      startLivePoll(matchId)
      if (opts?.fromUser) {
        ElMessage.info('棋盘战报同步中，请稍候再看')
      }
      return
    }
    liveOpen.value = true
    startLivePoll(matchId)
    return
  }
  // 已结束/无直播：尝试回放
  await hydrateBoardFromReport(matchId)
  if (boardReport.value) {
    liveOpen.value = true
    return
  }
  liveOpen.value = false
  watchingMatchId.value = null
  if (opts?.fromUser) {
    ElMessage.info('该场暂无棋盘战报（尚未开打或为旧场次）')
  }
}

async function onSelectMatch(match: DaoContestMatchPublic): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    if (match.status === 'adjusting' || match.status === 'pending') {
      if (match.live_active || match.can_spectate_live) {
        await openLive(match.id, { fromUser: true })
        return
      }
      ElMessage.info(
        match.status === 'adjusting'
          ? '整备中：请先改阵，开打后再看播报'
          : '该场尚未开打',
      )
      return
    }
    if (match.can_spectate_live || match.live_active || match.status === 'playing') {
      await openLive(match.id, { fromUser: true })
      return
    }
    stopLivePoll()
    daoLordStore.clearLive()
    watchingMatchId.value = match.id
    await hydrateBoardFromReport(match.id)
    if (!boardReport.value) {
      const reason =
        match.resolve_reason === 'bye'
          ? '轮空晋级，无对战战报'
          : '该场暂无棋盘战报（尚未开打或旧场次）'
      ElMessage.info(reason)
      watchingMatchId.value = null
      return
    }
    liveOpen.value = true
  } finally {
    busy.value = false
  }
}

/** 关窗：直播中场次记入 dismiss，赛程仍继续 */
function onDrawerBeforeClose(done: (cancel?: boolean) => void): void {
  const mid = watchingMatchId.value
  if (mid != null && live.value?.live_active) {
    const next = new Set(dismissedLiveMatchIds.value)
    next.add(mid)
    dismissedLiveMatchIds.value = next
    ElMessage.info('已关闭播报窗。点对阵表可再看，赛程仍继续。')
  }
  stopLivePoll()
  boardReport.value = null
  daoLordStore.clearLive()
  done()
}

async function onLeaveArena(): Promise<void> {
  if (busy.value) return
  busy.value = true
  intentionalLeave.value = true
  try {
    const forfeit = canLeaveForfeit.value
    const err = await daoLordStore.leaveArena(forfeit)
    if (err) {
      ElMessage.error(err)
      intentionalLeave.value = false
      return
    }
    if (forfeit) ElMessage.warning('演出中离场，已判负')
    else ElMessage.info('已离开擂台')
    await router.push('/hall')
  } finally {
    busy.value = false
  }
}

async function goFormation(): Promise<void> {
  if (!arena.value?.can_adjust_loadout) {
    ElMessage.warning(
      '当前不在入席确认/开赛倒计时/轮间/整备窗',
    )
    return
  }
  await router.push({ path: '/formation', query: { from: 'dao-arena' } })
}

onBeforeRouteLeave(async (_to, _from, next) => {
  if (intentionalLeave.value) {
    next()
    return
  }
  if (canLeaveForfeit.value) {
    const err = await daoLordStore.leaveArena(true)
    if (err) ElMessage.error(err)
    else ElMessage.warning('演出中离场，已判负')
  } else if (arena.value?.in_arena) {
    // 收口后仅清在席标记，不判负
    await daoLordStore.leaveArena(false)
  }
  next()
})

function onBeforeUnload(ev: BeforeUnloadEvent): void {
  if (!canLeaveForfeit.value) return
  ev.preventDefault()
  ev.returnValue = ''
  void daoLordStore.leaveArena(true)
}

onMounted(async () => {
  wsStore.connect()
  const err = await daoLordStore.enterArena()
  if (err) {
    ElMessage.warning(err)
    await daoLordStore.refreshArena()
  }
  await refresh()
  pollTimer = setInterval(() => {
    void refresh()
  }, 2000)
  window.addEventListener('beforeunload', onBeforeUnload)
})

onUnmounted(() => {
  stopTimers()
  window.removeEventListener('beforeunload', onBeforeUnload)
  daoLordStore.clearLive()
})

watch(
  () => daoLordStore.pendingLiveMatchId,
  async (id) => {
    if (id == null) return
    await openLive(id, { auto: true })
    daoLordStore.clearPendingLiveMatch()
  },
)
</script>

<template>
  <div class="arena-page">
    <AuthSessionBar />
    <div class="head">
      <el-button size="small" @click="router.push('/dao-lord?mode=contest')">← 赛会</el-button>
      <el-text tag="b" size="large">道主之争 · 擂台</el-text>
      <el-tag size="small">{{ phaseLabel }}</el-tag>
      <el-tag v-if="arena" type="warning" size="small">
        {{ syncedCountdown }}s
      </el-tag>
      <el-tag v-if="arena?.status === 'settled'" type="success" size="small">已收口</el-tag>
    </div>

    <el-alert
      v-if="loadoutHint"
      :title="loadoutHint"
      type="warning"
      :closable="false"
      show-icon
      class="banner"
    />
    <el-alert
      v-else-if="arena?.message_zh"
      :title="arena.message_zh"
      type="info"
      :closable="false"
      class="banner"
    />

    <el-alert
      v-if="liveDismissedHint"
      :title="liveDismissedHint"
      type="warning"
      :closable="false"
      show-icon
      class="banner"
    />

    <div class="actions">
      <el-button
        type="primary"
        :disabled="!arena?.can_adjust_loadout || busy"
        @click="goFormation"
      >
        调整上阵 / 阵法
      </el-button>
      <el-button
        v-if="liveDismissedHint && arena?.my_active_match"
        type="danger"
        :disabled="busy"
        @click="openLive(arena.my_active_match.id, { fromUser: true })"
      >
        回到播报
      </el-button>
      <el-button :disabled="busy" @click="refresh">刷新</el-button>
      <el-button type="danger" plain :disabled="busy" @click="onLeaveArena">
        离开擂台
      </el-button>
    </div>

    <DaoContestBracketBoard
      :matches="matches"
      :me-character-id="meCharacterId"
      :highlight-match-ids="highlightMatchIdList"
      @select="onSelectMatch"
    />

    <el-drawer
      v-model="liveOpen"
      :title="drawerTitle"
      size="92%"
      :close-on-click-modal="true"
      :close-on-press-escape="true"
      :show-close="true"
      :before-close="onDrawerBeforeClose"
    >
      <template v-if="live?.live_active || live?.phase === 'prep'">
        <el-alert
          :title="live.phase_label_zh || live.message || '直播中'"
          :type="live.phase === 'prep' ? 'warning' : 'error'"
          :closable="false"
        />
        <div v-if="live.phase === 'prep'" class="prep">
          <div class="countdown">{{ livePrepCountdown }}</div>
          <el-text>入席确认 · 布阵已锁定 · 开战将以棋盘动画演出</el-text>
          <div v-if="live.formation_visible && live.formation" class="formation">
            <el-text tag="b">布阵锁定（仅选手可见）</el-text>
            <ul>
              <li>
                {{ live.formation.side_a?.name || '甲方' }}：{{ live.formation.side_a?.label_zh }}
              </li>
              <li>
                {{ live.formation.side_b?.name || '乙方' }}：{{ live.formation.side_b?.label_zh }}
              </li>
            </ul>
          </div>
        </div>
      </template>

      <BattleReportPlayer
        v-if="showBoardPlayer"
        :report="boardReport"
        :playback-policy="boardPlaybackPolicy"
        :live-event-cursor="liveEventCursor"
        :board-top-label="boardView?.topLabel"
        :board-bottom-label="boardView?.bottomLabel"
        class="board-player"
      />
      <!-- 无棋盘时不渲染 empty，避免「暂无棋盘战报」空窗 -->

      <el-text v-if="live?.live_active" type="info" size="small" class="footer-hint">
        直播中不可跳过，请等待播报结束
      </el-text>
    </el-drawer>
  </div>
</template>

<style scoped>
.arena-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.banner {
  margin: 0;
}
.prep {
  text-align: center;
  padding: 1.5rem 0;
}
.countdown {
  font-size: 3rem;
  font-weight: 700;
}
.formation {
  text-align: left;
  margin: 1rem auto 0;
  max-width: 22rem;
  padding: 0.75rem 1rem;
  background: rgba(0, 0, 0, 0.04);
}
.formation ul {
  margin: 0.5rem 0;
  padding-left: 1.1rem;
}
.board-player {
  margin-top: 0.75rem;
}
.footer-hint {
  display: block;
  margin-top: 0.75rem;
}
</style>
