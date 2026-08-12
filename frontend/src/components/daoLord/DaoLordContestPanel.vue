<script setup lang="ts">
/**
 * 道主之争：报名 + 分组对战表 + 棋盘直播/回放。
 */
import { computed, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import BattleReportPlayer from '../battle/BattleReportPlayer.vue'
import DaoContestBracketBoard from './DaoContestBracketBoard.vue'
import { useDaoLordStore } from '../../stores/daoLord'
import type { DaoContestMatchPublic } from '../../types/daoLord'
import type { AutochessBattleResult, PlaybackPolicy } from '../../types/autochess'
import { DEFAULT_EXPLORATION_PLAYBACK_POLICY } from '../../types/autochess'
import {
  boardViewFromResult,
  contestReportToBattleResult,
} from '../../utils/contestBattleReport'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const daoLordStore = useDaoLordStore()
const busy = ref(false)
const liveOpen = ref(false)
const watchingMatchId = ref<number | null>(null)
const boardReport = ref<AutochessBattleResult | null>(null)
/** 用户关掉的直播场次，关后不再被 pendingLive 强制打开 */
const dismissedLiveMatchIds = ref<Set<number>>(new Set())
let liveTimer: ReturnType<typeof setInterval> | null = null

const contest = computed(() => daoLordStore.contest?.contest ?? null)
const me = computed(() => daoLordStore.contest?.me ?? null)
const matches = computed(() => daoLordStore.bracket?.matches ?? [])
const live = computed(() => daoLordStore.liveState)
const meCharacterId = computed(
  () => daoLordStore.bracket?.me_character_id ?? null,
)
const boardView = computed(() => boardViewFromResult(boardReport.value))
const liveEventCursor = computed(() => live.value?.battle_event_cursor ?? 0)

/** 播控策略：优先直播态，其次 match report，再次战报信封；缺省探索兜底 */
const boardPlaybackPolicy = computed<PlaybackPolicy>(() => {
  const fromLive = live.value?.playback_policy
  if (fromLive) return fromLive
  const fromMatch = daoLordStore.matchReport?.playback_policy
  if (fromMatch) return fromMatch
  return boardReport.value?.playback_policy ?? DEFAULT_EXPLORATION_PLAYBACK_POLICY
})

const counts = computed(() =>
  (contest.value?.counts_by_dao || []).filter((row) => row.count > 0),
)

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

watch(
  () => contest.value?.bracket_ready,
  async (ready) => {
    if (ready) {
      await daoLordStore.refreshBracket(me.value?.dao_id || undefined)
    }
  },
  { immediate: true },
)

/** 开赛推送：自动打开本人（或任意）直播中的对阵 */
watch(
  () => [daoLordStore.pendingLiveMatchId, matches.value] as const,
  async ([matchId]) => {
    if (matchId == null) return
    if (dismissedLiveMatchIds.value.has(matchId)) {
      daoLordStore.clearPendingLiveMatch()
      return
    }
    const match = matches.value.find((m) => m.id === matchId)
    if (!match) return
    if (watchingMatchId.value === matchId && liveOpen.value) {
      daoLordStore.clearPendingLiveMatch()
      return
    }
    await openMatch(match, { auto: true })
    if (daoLordStore.pendingLiveMatchId === matchId) {
      daoLordStore.clearPendingLiveMatch()
    }
  },
)

function stopLivePoll(): void {
  if (liveTimer) {
    clearInterval(liveTimer)
    liveTimer = null
  }
}

onUnmounted(() => {
  stopLivePoll()
  daoLordStore.clearLive()
})

async function onRegister(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await daoLordStore.registerContest()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(daoLordStore.lastMessage || '报名成功')
    emit('log', daoLordStore.lastMessage || '报名成功', 'success')
  } finally {
    busy.value = false
  }
}

async function onUnregister(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await daoLordStore.unregisterContest()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(daoLordStore.lastMessage || '已取消报名')
    emit('log', daoLordStore.lastMessage || '已取消报名', 'info')
  } finally {
    busy.value = false
  }
}

async function onRefreshAll(): Promise<void> {
  busy.value = true
  try {
    await daoLordStore.refreshContest()
    if (contest.value?.bracket_ready) {
      await daoLordStore.refreshBracket(me.value?.dao_id || undefined)
    }
  } finally {
    busy.value = false
  }
}

async function hydrateBoardFromReport(matchId: number): Promise<string | null> {
  const err = await daoLordStore.loadMatchReport(matchId)
  if (err) {
    boardReport.value = null
    return err
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
  return null
}

function startLivePoll(matchId: number): void {
  stopLivePoll()
  watchingMatchId.value = matchId
  liveTimer = setInterval(async () => {
    if (watchingMatchId.value == null) return
    if (!liveOpen.value && dismissedLiveMatchIds.value.has(matchId)) {
      stopLivePoll()
      return
    }
    await daoLordStore.pollLive(watchingMatchId.value)
    const state = daoLordStore.liveState
    if (state?.phase === 'battle' && !boardReport.value) {
      await hydrateBoardFromReport(matchId)
    }
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
      dismissedLiveMatchIds.value.delete(matchId)
      dismissedLiveMatchIds.value = new Set(dismissedLiveMatchIds.value)
    }
  }, 500)
}

async function openMatch(
  match: DaoContestMatchPublic,
  opts?: { auto?: boolean },
): Promise<void> {
  busy.value = true
  try {
    if (match.status === 'adjusting' || match.status === 'pending') {
      if (!(match.live_active || match.can_spectate_live)) {
        const reason =
          match.status === 'adjusting'
            ? '整备中：请先改阵，开打后再看播报'
            : '该场尚未开打'
        ElMessage.info(reason)
        emit('log', reason, 'info')
        return
      }
    }
    if (match.can_spectate_live || match.live_active) {
      if (opts?.auto && dismissedLiveMatchIds.value.has(match.id)) {
        return
      }
      if (!opts?.auto) {
        const next = new Set(dismissedLiveMatchIds.value)
        next.delete(match.id)
        dismissedLiveMatchIds.value = next
      }
      const err = await daoLordStore.spectateMatch(match.id)
      if (err) {
        ElMessage.error(err)
        emit('log', err, 'warning')
        return
      }
      boardReport.value = null
      await daoLordStore.pollLive(match.id)
      const state = daoLordStore.liveState
      const isPrep = Boolean(state?.live_active && state?.phase === 'prep')
      const isBattle = Boolean(state?.live_active && state?.phase === 'battle')
      if (isPrep) {
        liveOpen.value = true
        startLivePoll(match.id)
        emit('log', daoLordStore.lastMessage || '进入直播准备', 'system')
        return
      }
      if (isBattle) {
        await hydrateBoardFromReport(match.id)
        if (!boardReport.value) {
          startLivePoll(match.id)
          if (!opts?.auto) {
            ElMessage.info('棋盘战报同步中，请稍候再看')
          }
          return
        }
        liveOpen.value = true
        startLivePoll(match.id)
        emit('log', daoLordStore.lastMessage || '进入直播', 'system')
        return
      }
      // 直播已结束：走回放
    }
    // 回放：有棋盘战报才开抽屉
    stopLivePoll()
    daoLordStore.clearLive()
    watchingMatchId.value = match.id
    const err = await hydrateBoardFromReport(match.id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      watchingMatchId.value = null
      return
    }
    if (!boardReport.value) {
      const reason =
        match.resolve_reason === 'bye'
          ? '轮空晋级，无对战战报'
          : '该场暂无棋盘战报（尚未开打或旧场次）'
      ElMessage.info(reason)
      emit('log', reason, 'info')
      watchingMatchId.value = null
      return
    }
    liveOpen.value = true
  } finally {
    busy.value = false
  }
}

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
</script>

<template>
  <el-card shadow="never" class="contest">
    <template #header>
      <el-text tag="b">道主之争</el-text>
    </template>

    <el-empty v-if="!contest" description="暂无赛会数据" :image-size="48" />

    <template v-else>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="`${contest.status_label} · ${contest.eta_label}`"
      />
      <el-descriptions :column="1" size="small" class="meta" border>
        <el-descriptions-item label="业务日">{{ contest.cycle_date }}</el-descriptions-item>
        <el-descriptions-item label="开战">
          {{ contest.fight_at ? new Date(contest.fight_at).toLocaleString('zh-CN') : '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="已报名">{{ contest.total_entrants }} 人</el-descriptions-item>
        <el-descriptions-item label="对阵">{{ contest.match_count ?? 0 }} 场</el-descriptions-item>
        <el-descriptions-item label="本人">
          <span v-if="me?.registered">已报名（{{ me.dao_label || me.dao_id }}）</span>
          <span v-else-if="me?.eligible === false">
            不可报名{{ me.eligible_block_reason ? `：${me.eligible_block_reason}` : '' }}
          </span>
          <span v-else>未报名</span>
        </el-descriptions-item>
      </el-descriptions>

      <div v-if="counts.length" class="counts">
        <el-text size="small" type="info">分道人数</el-text>
        <ul>
          <li v-for="row in counts" :key="row.dao_id">
            {{ row.dao_label }}：{{ row.count }}
          </li>
        </ul>
      </div>

      <div class="actions">
        <el-button
          v-if="!me?.registered && (me?.can_register ?? contest.can_register)"
          type="primary"
          :loading="busy"
          @click="onRegister"
        >
          报名
        </el-button>
        <el-button
          v-else-if="me?.registered"
          type="warning"
          :loading="busy"
          :disabled="contest.status !== 'registration'"
          @click="onUnregister"
        >
          取消报名
        </el-button>
        <el-button :loading="busy" @click="onRefreshAll">刷新</el-button>
      </div>

      <div v-if="matches.length" class="bracket">
        <DaoContestBracketBoard
          :matches="matches"
          :me-character-id="meCharacterId"
          @select="openMatch"
        />
      </div>
    </template>

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
          :type="live.phase === 'prep' ? 'warning' : 'error'"
          :closable="false"
          :title="live.phase_label_zh || live.message || '直播中'"
        />

        <div v-if="live.phase === 'prep'" class="prep">
          <div class="countdown">{{ live.countdown_seconds }}</div>
          <p class="prep-hint">
            <template v-if="live.viewer_role === 'spectator'">
              {{ live.spectator_prep_hint_zh || '双方准备中。' }}
              <br />
              <el-text type="info" size="small">观众不可见布阵</el-text>
            </template>
            <template v-else>
              入席确认 · 布阵已锁定 · 开战将以棋盘动画演出
            </template>
          </p>
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
            <el-text size="small" type="info">{{ live.formation.hint_zh }}</el-text>
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
        直播中不可跳过，请等待窗口结束
      </el-text>
    </el-drawer>
  </el-card>
</template>

<style scoped>
.meta {
  margin-top: 0.75rem;
}
.counts {
  margin-top: 0.75rem;
}
.counts ul {
  margin: 0.25rem 0 0;
  padding-left: 1.25rem;
}
.actions {
  margin-top: 0.75rem;
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.bracket {
  margin-top: 0.75rem;
}
.prep {
  text-align: center;
  margin-top: 1.25rem;
}
.countdown {
  font-size: 3.5rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  line-height: 1.1;
}
.prep-hint {
  margin: 0.75rem 0 1rem;
  line-height: 1.6;
}
.formation {
  text-align: left;
  margin: 0 auto;
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
  margin-top: 1rem;
}
</style>
