<script setup lang="ts">
/**
 * 轮回 / 待引渡 / 新生页（M5 · /reincarnation）。
 * query.mode = ferry | altar | logs | newborn
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import AltarConfirmPanel from '../components/reincarnation/AltarConfirmPanel.vue'
import FerryActionsPanel from '../components/reincarnation/FerryActionsPanel.vue'
import FerryCountdownPanel from '../components/reincarnation/FerryCountdownPanel.vue'
import NewbornSetupPanel from '../components/reincarnation/NewbornSetupPanel.vue'
import ReincarnationPreviewPanel from '../components/reincarnation/ReincarnationPreviewPanel.vue'
import StoryFlagsReadonly from '../components/reincarnation/StoryFlagsReadonly.vue'
import { useCharacterStore } from '../stores/character'
import { useFerryStore } from '../stores/ferry'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'

type Mode = 'ferry' | 'altar' | 'logs' | 'newborn'

const route = useRoute()
const router = useRouter()
const characterStore = useCharacterStore()
const ferryStore = useFerryStore()

const loadError = ref('')
const logEntries = ref<GameLogEntry[]>([])
const navigating = ref(false)

const reincarnating = computed(
  () => characterStore.character?.status === 'reincarnating',
)
const awaitingFerry = computed(
  () => characterStore.character?.status === 'awaiting_ferry',
)

const mode = computed<Mode>(() => {
  // 新生态强制新生页
  if (reincarnating.value) return 'newborn'
  const m = route.query.mode
  if (m === 'altar' || m === 'logs' || m === 'ferry' || m === 'newborn') return m
  if (awaitingFerry.value) return 'ferry'
  return 'altar'
})

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logEntries.value = [...logEntries.value.slice(-49), createLogEntry(message, level)]
}

function setMode(next: string | number | boolean | undefined): void {
  if (reincarnating.value) {
    void router.replace({ name: 'reincarnation', query: { mode: 'newborn' } })
    return
  }
  const m = String(next)
  if (m === 'altar' || m === 'logs' || m === 'ferry' || m === 'newborn') {
    void router.replace({ name: 'reincarnation', query: { mode: m } })
  }
}

/** 回大厅：新生态不可离开；待引渡可只读进厅 */
async function goHall(): Promise<void> {
  if (reincarnating.value) {
    ElMessage.warning('请先完成新生选角后再进入大厅')
    return
  }
  if (navigating.value) return
  navigating.value = true
  try {
    await router.push({ name: 'hall' })
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '无法返回大厅'
    ElMessage.error(message)
    pushLog(message, 'warning')
  } finally {
    navigating.value = false
  }
}

async function refreshAll(): Promise<void> {
  await characterStore.fetchMe()
  if (characterStore.character?.status === 'awaiting_ferry') {
    const err = await ferryStore.loadFerry()
    if (err) loadError.value = err
    else loadError.value = ''
  } else {
    ferryStore.ferry = null
  }
  await ferryStore.loadLogs()
  // 轮回结算后进入新生
  if (characterStore.character?.status === 'reincarnating') {
    await router.replace({ name: 'reincarnation', query: { mode: 'newborn' } })
  }
}

async function onExpired(): Promise<void> {
  pushLog('引渡时限已至，正在校准…', 'warning')
  await refreshAll()
  if (characterStore.character?.status === 'reincarnating') {
    ElMessage.info('已强制轮回，请完成新生选角')
    pushLog('超时强制轮回 → 新生', 'system')
    return
  }
  if (characterStore.character?.status !== 'awaiting_ferry') {
    ElMessage.info('服务器已结算轮回')
    pushLog('超时强制轮回已结算', 'system')
    setMode('logs')
  }
}

async function onNewbornCompleted(): Promise<void> {
  pushLog('新生完成，进入本世', 'success')
  await characterStore.fetchMe()
  await router.replace({ name: 'hall' })
}

async function ensureModeData(m: Mode): Promise<void> {
  loadError.value = ''
  if (m === 'newborn') return
  if (m === 'ferry') {
    if (awaitingFerry.value) {
      const err = await ferryStore.loadFerry()
      if (err) loadError.value = err
      const previewErr = await ferryStore.loadPreview('voluntary_ferry')
      if (previewErr && !loadError.value) loadError.value = previewErr
    }
    return
  }
  if (m === 'altar') {
    const err = await ferryStore.loadPreview('altar')
    if (err) loadError.value = err
    return
  }
  if (m === 'logs') {
    const err = await ferryStore.loadLogs()
    if (err) loadError.value = err
  }
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
  if (reincarnating.value) {
    await router.replace({ name: 'reincarnation', query: { mode: 'newborn' } })
    return
  }
  if (!route.query.mode) {
    const defaultMode = awaitingFerry.value ? 'ferry' : 'altar'
    await router.replace({ name: 'reincarnation', query: { mode: defaultMode } })
  }
  try {
    await ensureModeData(mode.value)
    if (mode.value !== 'logs' && mode.value !== 'newborn') {
      await ferryStore.loadLogs()
    }
  } catch (e: unknown) {
    loadError.value = e instanceof Error ? e.message : '加载失败'
  }
})

watch(mode, (m) => {
  void ensureModeData(m)
})

watch(reincarnating, (v) => {
  if (v) void router.replace({ name: 'reincarnation', query: { mode: 'newborn' } })
})
</script>

<template>
  <div class="reincarnation-page">
    <AuthSessionBar />

    <div class="page-title">
      <el-button
        size="small"
        type="primary"
        plain
        :loading="navigating"
        :disabled="reincarnating"
        @click="goHall"
      >
        ← 回大厅
      </el-button>
      <el-text tag="b" size="large">轮回与引渡</el-text>
      <el-text type="info" size="small">M5</el-text>
      <el-tag v-if="awaitingFerry" type="danger" size="small" effect="dark">
        待引渡中（大厅可只读）
      </el-tag>
      <el-tag v-if="reincarnating" type="warning" size="small" effect="dark">
        新生选角中
      </el-tag>
    </div>

    <el-radio-group
      :model-value="mode"
      size="small"
      class="mode-tabs"
      :disabled="reincarnating"
      @change="setMode"
    >
      <el-radio-button value="ferry" :disabled="reincarnating">待引渡</el-radio-button>
      <el-radio-button value="altar" :disabled="awaitingFerry || reincarnating">
        祭坛
      </el-radio-button>
      <el-radio-button value="newborn" :disabled="!reincarnating && mode !== 'newborn'">
        新生
      </el-radio-button>
      <el-radio-button value="logs" :disabled="reincarnating">流水 / 阅历</el-radio-button>
    </el-radio-group>

    <el-alert
      v-if="awaitingFerry && mode === 'altar'"
      title="待引渡中不可使用祭坛；请先自救或进入轮回"
      type="warning"
      show-icon
      :closable="false"
      class="page-alert"
    />

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="true"
      class="page-alert"
      @close="loadError = ''"
    />

    <div v-if="mode === 'newborn'" class="mode-body">
      <NewbornSetupPanel @log="pushLog" @completed="onNewbornCompleted" />
    </div>

    <div v-else-if="mode === 'ferry'" class="mode-body">
      <template v-if="awaitingFerry">
        <FerryCountdownPanel
          :deadline-at="ferryStore.deadlineAt || characterStore.character?.ferry?.deadline_at"
          @expired="onExpired"
        />
        <FerryActionsPanel
          @log="pushLog"
          @rescued="refreshAll"
          @reincarnated="refreshAll"
        />
        <ReincarnationPreviewPanel
          :preview="ferryStore.preview"
          :loading="ferryStore.loading"
        />
      </template>
      <el-empty v-else description="当前非待引渡状态；可前往祭坛主动轮回">
        <el-button type="primary" @click="setMode('altar')">打开祭坛</el-button>
      </el-empty>
    </div>

    <div v-else-if="mode === 'altar'" class="mode-body">
      <template v-if="!awaitingFerry && !reincarnating">
        <ReincarnationPreviewPanel
          :preview="ferryStore.preview"
          :loading="ferryStore.loading"
        />
        <AltarConfirmPanel @log="pushLog" @done="refreshAll" />
      </template>
      <el-empty v-else description="待引渡中请使用「待引渡」页签">
        <el-button type="warning" @click="setMode('ferry')">前往待引渡</el-button>
      </el-empty>
    </div>

    <div v-else class="mode-body">
      <StoryFlagsReadonly :logs="ferryStore.logs" />
    </div>
  </div>
</template>

<style scoped>
.reincarnation-page {
  max-width: 720px;
  margin: 0 auto;
  padding: 1rem 1rem 2rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.mode-tabs {
  margin-bottom: 0.25rem;
}

.mode-body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.page-alert {
  margin-bottom: 0.25rem;
}
</style>
