<script setup lang="ts">
/**
 * 大道页（M6 · /dao）：开道 / 道池 / 道资源。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import DaoOpenPanel from '../components/dao/DaoOpenPanel.vue'
import DaoPoolGallery from '../components/dao/DaoPoolGallery.vue'
import DaoRestraintHint from '../components/dao/DaoRestraintHint.vue'
import DaoStatusPanel from '../components/dao/DaoStatusPanel.vue'
import DaoUsageToggle from '../components/dao/DaoUsageToggle.vue'
import { useCharacterStore } from '../stores/character'
import { useDaoStore } from '../stores/dao'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'

const route = useRoute()
const router = useRouter()
const characterStore = useCharacterStore()
const daoStore = useDaoStore()

const loadError = ref('')
const logEntries = ref<GameLogEntry[]>([])

const mode = computed(() => {
  const m = route.query.mode
  return m === 'pool' || m === 'open' ? m : 'open'
})

const focusId = computed(() =>
  typeof route.query.focus === 'string' ? route.query.focus : null,
)

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logEntries.value = [...logEntries.value.slice(-49), createLogEntry(message, level)]
}

function setMode(next: 'open' | 'pool'): void {
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
  daoStore.applyMeFromCharacter()
  const err = await daoStore.refresh()
  if (err) {
    loadError.value = err
    pushLog(err, 'warning')
  } else {
    pushLog('大道页已就绪：开道权威在服务端。', 'info')
  }
  daoStore.startPoll()
})

onUnmounted(() => {
  daoStore.stopPoll()
})

watch(
  () => characterStore.character?.dao,
  () => {
    daoStore.applyMeFromCharacter()
  },
)
</script>

<template>
  <div class="dao-page">
    <AuthSessionBar />

    <div class="page-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-text tag="b" size="large">大道</el-text>
      <el-text type="info" size="small">M6 · 开道 / 道池 / 运用偏好</el-text>
      <div class="mode-nav">
        <el-button
          size="small"
          :type="mode === 'open' ? 'primary' : 'default'"
          @click="setMode('open')"
        >
          开道
        </el-button>
        <el-button
          size="small"
          :type="mode === 'pool' ? 'primary' : 'default'"
          @click="setMode('pool')"
        >
          道池图鉴
        </el-button>
        <el-button size="small" @click="router.push('/dao-lord')">道主</el-button>
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

    <DaoStatusPanel :dao="daoStore.me" />

    <div class="main-grid">
      <div class="main-left">
        <DaoOpenPanel
          v-if="mode === 'open'"
          @log="pushLog"
          @chosen="pushLog(daoStore.lastMessage || '开道成功', 'success')"
        />
        <DaoPoolGallery
          v-else
          :catalog="daoStore.catalog"
          :focus-id="focusId"
        />
      </div>
      <aside class="main-side">
        <DaoRestraintHint />
        <DaoUsageToggle />
        <el-card v-if="logEntries.length" shadow="never">
          <template #header>
            <el-text tag="b" size="small">本页日志</el-text>
          </template>
          <div v-for="e in logEntries.slice(-8)" :key="e.id" class="log-line">
            <el-text size="small">{{ e.message }}</el-text>
          </div>
        </el-card>
      </aside>
    </div>

    <DaoPoolGallery
      v-if="mode === 'open'"
      class="pool-below"
      :catalog="daoStore.catalog"
      :focus-id="focusId"
    />
  </div>
</template>

<style scoped>
.dao-page {
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

.main-grid {
  display: grid;
  grid-template-columns: 1fr minmax(220px, 300px);
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.main-left,
.main-side {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-width: 0;
}

.pool-below {
  margin-top: 0.75rem;
}

.log-line {
  padding: 0.15rem 0;
}

@media (max-width: 800px) {
  .main-grid {
    grid-template-columns: 1fr;
  }
}
</style>
