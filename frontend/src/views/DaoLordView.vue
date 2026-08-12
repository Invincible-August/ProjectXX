<script setup lang="ts">
/**
 * 道主页（M6 · /dao-lord）：榜单 / 赛会报名 / 事件骨架。
 * 旧即时单挑（challenges）已移除，有主更替仅走道主之争赛会。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import DaoLordBoardPanel from '../components/daoLord/DaoLordBoardPanel.vue'
import DaoLordContestPanel from '../components/daoLord/DaoLordContestPanel.vue'
import DaoLordWindowBanner from '../components/daoLord/DaoLordWindowBanner.vue'
import WorldEventSkeletonPanel from '../components/daoLord/WorldEventSkeletonPanel.vue'
import { useCharacterStore } from '../stores/character'
import { useDaoLordStore } from '../stores/daoLord'
import { useWorldEventsStore } from '../stores/worldEvents'
import { useWsStore } from '../stores/ws'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'

const route = useRoute()
const router = useRouter()
const characterStore = useCharacterStore()
const daoLordStore = useDaoLordStore()
const eventsStore = useWorldEventsStore()
const wsStore = useWsStore()

const loadError = ref('')
const logEntries = ref<GameLogEntry[]>([])
let unsubWs: (() => void) | null = null

const mode = computed(() => {
  const m = route.query.mode
  // 兼容旧链接 ?mode=challenge → 榜单；spectate → 赛会（观战嵌在赛会/擂台）
  if (m === 'challenge') return 'board'
  if (m === 'spectate') return 'contest'
  if (m === 'events' || m === 'board' || m === 'contest') return m
  return 'board'
})

const focusDao = computed(() =>
  typeof route.query.dao === 'string' ? route.query.dao : null,
)

const wsReady = computed(() => wsStore.enabled)

/** 未达标时不展示「去报名 / 道主之争报名」入口 */
const showContestRegister = computed(() => {
  const me = daoLordStore.contest?.me
  if (me?.registered) return true
  if (me?.eligible === false) return false
  if (me?.can_register) return true
  return daoLordStore.board.some(
    (s) => Boolean(s.lord_character_id && !s.is_self_lord && s.can_challenge),
  )
})

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logEntries.value = [...logEntries.value.slice(-49), createLogEntry(message, level)]
}

function setMode(next: 'board' | 'contest' | 'events'): void {
  void router.replace({ query: { ...route.query, mode: next } })
}

onMounted(async () => {
  loadError.value = ''
  if (!characterStore.character) {
    const ok = await characterStore.fetchMe()
    if (!ok) {
      await router.replace('/create-character')
      return
    }
  }
  if (characterStore.character?.status === 'awaiting_ferry') {
    await router.replace('/reincarnation?mode=ferry')
    return
  }

  // 旧单挑深链 → 榜单；观战深链 → 赛会
  if (route.query.mode === 'challenge') {
    void router.replace({ query: { ...route.query, mode: 'board' } })
  } else if (route.query.mode === 'spectate') {
    void router.replace({ query: { ...route.query, mode: 'contest' } })
  }

  wsStore.connect()
  unsubWs = wsStore.subscribe((env) => {
    daoLordStore.onWsEnvelope(env)
  })

  const err = await daoLordStore.refresh()
  if (err) {
    loadError.value = err
    pushLog(err, 'warning')
  } else {
    pushLog('道主榜已加载。', 'info')
    if (daoLordStore.lastMessage) {
      ElMessage.success(daoLordStore.lastMessage)
      pushLog(daoLordStore.lastMessage, 'success')
      await characterStore.fetchMe()
    }
  }

  if (mode.value === 'events') {
    const e2 = await eventsStore.refresh()
    if (e2) pushLog(e2, 'warning')
  }
})

onUnmounted(() => {
  unsubWs?.()
  unsubWs = null
})

watch(
  () => daoLordStore.contestKickSignal,
  (n, prev) => {
    if (!n || n === prev) return
    setMode('contest')
    if (daoLordStore.lastMessage) {
      pushLog(daoLordStore.lastMessage, 'system')
    }
  },
)

watch(mode, async (m) => {
  if (m === 'events' && !eventsStore.events.length) {
    const e = await eventsStore.refresh()
    if (e) pushLog(e, 'warning')
  }
  if (m === 'contest') {
    const e = await daoLordStore.refreshContest()
    if (e) pushLog(e, 'warning')
  }
})
</script>

<template>
  <div class="dao-lord-page">
    <AuthSessionBar />

    <div class="page-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-text tag="b" size="large">道主之争</el-text>
      <el-text type="info" size="small">M6 · 榜单 / 报名 / 事件</el-text>
      <div class="mode-nav">
        <el-button
          size="small"
          :type="mode === 'board' ? 'primary' : 'default'"
          @click="setMode('board')"
        >
          道主榜
        </el-button>
        <el-button
          size="small"
          :type="mode === 'contest' ? 'primary' : 'default'"
          @click="setMode('contest')"
        >
          道主之争
        </el-button>
        <el-button
          size="small"
          :type="mode === 'events' ? 'warning' : 'default'"
          @click="setMode('events')"
        >
          事件骨架
        </el-button>
        <el-button size="small" @click="router.push('/dao')">大道</el-button>
      </div>
    </div>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
      class="page-alert"
    />

    <DaoLordWindowBanner
      :window="daoLordStore.window"
      @expired="daoLordStore.refreshWindow()"
    />

    <DaoLordBoardPanel
      v-if="mode === 'board'"
      :seats="daoLordStore.board"
      :window-open="daoLordStore.isWindowOpen"
      :ws-ready="wsReady"
      :focus-dao-id="focusDao"
      :busy="daoLordStore.loading"
      :show-contest-register="showContestRegister"
      @contest="setMode('contest')"
    />

    <DaoLordContestPanel v-else-if="mode === 'contest'" @log="pushLog" />

    <WorldEventSkeletonPanel v-else @log="pushLog" />

    <el-card v-if="logEntries.length" shadow="never" class="mt">
      <template #header>
        <el-text tag="b" size="small">本页日志</el-text>
      </template>
      <div v-for="e in logEntries.slice(-8)" :key="e.id" class="log-line">
        <el-text size="small">{{ e.message }}</el-text>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.dao-lord-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 1rem 1rem 2rem;
}

.page-title {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.5rem 0.75rem;
  margin: 0.75rem 0 1rem;
}

.mode-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-left: auto;
}

.page-alert {
  margin-bottom: 0.75rem;
}

.mt {
  margin-top: 0.75rem;
}

.log-line {
  padding: 0.15rem 0;
}
</style>
