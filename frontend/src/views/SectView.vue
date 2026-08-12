<script setup lang="ts">
/**
 * 宗门页（M7 L1 · /sect）：拜入 / 状态 / 任务 / 商店 / 魂灯 / 兑宠。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import SectJoinCreatePanel from '../components/sect/SectJoinCreatePanel.vue'
import SectPetExchangePanel from '../components/sect/SectPetExchangePanel.vue'
import SectQuestPanel from '../components/sect/SectQuestPanel.vue'
import SectShopPanel from '../components/sect/SectShopPanel.vue'
import SectSoulLampPanel from '../components/sect/SectSoulLampPanel.vue'
import SectStatusPanel from '../components/sect/SectStatusPanel.vue'
import { useCharacterStore } from '../stores/character'
import { useSectStore } from '../stores/sect'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'

/** 合法 mode 集合 */
type SectMode = 'join' | 'status' | 'quests' | 'shop' | 'lamps' | 'exchange'

const MODE_SET = new Set<string>([
  'join',
  'status',
  'quests',
  'shop',
  'lamps',
  'exchange',
])

const route = useRoute()
const router = useRouter()
const characterStore = useCharacterStore()
const sectStore = useSectStore()

const loadError = ref('')
const logEntries = ref<GameLogEntry[]>([])

const mode = computed<SectMode>(() => {
  const m = route.query.mode
  if (typeof m === 'string' && MODE_SET.has(m)) {
    return m as SectMode
  }
  // 无合法 mode：散修默认 join，入宗默认 status
  return sectStore.inSect ? 'status' : 'join'
})

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logEntries.value = [...logEntries.value.slice(-49), createLogEntry(message, level)]
}

function setMode(next: SectMode): void {
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
  sectStore.applyMeFromCharacter()
  const err = await sectStore.refresh()
  if (err) {
    loadError.value = err
    pushLog(err, 'warning')
  } else {
    pushLog('宗门页已就绪：拜入与贡献权威在服务端。', 'info')
  }
  // 首次进入无 mode 时写入默认 query，便于分享深链
  if (!MODE_SET.has(String(route.query.mode ?? ''))) {
    const def: SectMode = sectStore.inSect ? 'status' : 'join'
    void router.replace({ query: { ...route.query, mode: def } })
  }
})

watch(
  () => characterStore.character?.sect,
  () => {
    sectStore.applyMeFromCharacter()
  },
)

function onJoined(): void {
  pushLog(sectStore.lastMessage || '入宗成功', 'success')
  setMode('status')
}
</script>

<template>
  <div class="sect-page">
    <AuthSessionBar />

    <div class="page-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-text tag="b" size="large">宗门</el-text>
      <el-text type="info" size="small">M7 L1 · 拜入 / 任务 / 商店 / 魂灯 / 兑宠</el-text>
      <div class="mode-nav">
        <el-button
          size="small"
          :type="mode === 'join' ? 'primary' : 'default'"
          @click="setMode('join')"
        >
          拜入/建宗
        </el-button>
        <el-button
          size="small"
          :type="mode === 'status' ? 'primary' : 'default'"
          @click="setMode('status')"
        >
          状态
        </el-button>
        <el-button
          size="small"
          :type="mode === 'quests' ? 'primary' : 'default'"
          :disabled="!sectStore.inSect"
          @click="setMode('quests')"
        >
          任务
        </el-button>
        <el-button
          size="small"
          :type="mode === 'shop' ? 'primary' : 'default'"
          :disabled="!sectStore.inSect"
          @click="setMode('shop')"
        >
          商店
        </el-button>
        <el-button
          size="small"
          :type="mode === 'lamps' ? 'primary' : 'default'"
          @click="setMode('lamps')"
        >
          魂灯
        </el-button>
        <el-button
          size="small"
          :type="mode === 'exchange' ? 'primary' : 'default'"
          @click="setMode('exchange')"
        >
          兑宠
        </el-button>
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

    <SectStatusPanel :sect="sectStore.me" />

    <div class="main-grid">
      <div class="main-left">
        <SectJoinCreatePanel
          v-if="mode === 'join'"
          @log="pushLog"
          @joined="onJoined"
        />
        <el-card v-else-if="mode === 'status'" shadow="never">
          <template #header>
            <el-text tag="b">宗门概览</el-text>
          </template>
          <el-text v-if="sectStore.inSect">
            可在上方切换任务、商店、魂灯与兑宠。贡献与解锁以服务端为准。
          </el-text>
          <el-text v-else type="warning">
            你仍是散修。请先「拜入/建宗」，入宗后挂机修为占位提升。
          </el-text>
        </el-card>
        <SectQuestPanel v-else-if="mode === 'quests'" @log="pushLog" />
        <SectShopPanel v-else-if="mode === 'shop'" @log="pushLog" />
        <template v-else-if="mode === 'lamps'">
          <el-empty
            v-if="!sectStore.inSect"
            description="入宗后可查看同门魂灯状态"
            :image-size="64"
          />
          <SectSoulLampPanel v-else @log="pushLog" />
        </template>
        <SectPetExchangePanel v-else-if="mode === 'exchange'" @log="pushLog" />
      </div>
      <aside class="main-side">
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
  </div>
</template>

<style scoped>
.sect-page {
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

.log-line {
  padding: 0.15rem 0;
}

@media (max-width: 800px) {
  .main-grid {
    grid-template-columns: 1fr;
  }
}
</style>
