<script setup lang="ts">
/**
 * 工坊页（M4 · /workshop）：配方 / 队列 / 领取 / 背包。
 */
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import StaminaBar from '../components/battle/StaminaBar.vue'
import CraftClaimBar from '../components/workshop/CraftClaimBar.vue'
import CraftEnvHint from '../components/workshop/CraftEnvHint.vue'
import CraftDaoUsageLine from '../components/workshop/CraftDaoUsageLine.vue'
import CraftJobQueue from '../components/workshop/CraftJobQueue.vue'
import InventoryPanel from '../components/workshop/InventoryPanel.vue'
import RecipeList from '../components/workshop/RecipeList.vue'
import { useCraftStore } from '../stores/craft'
import { useCharacterStore } from '../stores/character'
import { useInventoryStore } from '../stores/inventory'
import type { CraftActor } from '../types/craft'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'

const route = useRoute()
const router = useRouter()
const craftStore = useCraftStore()
const characterStore = useCharacterStore()
const inventoryStore = useInventoryStore()

const loadError = ref('')
const logEntries = ref<GameLogEntry[]>([])
const initialBranch = ref(typeof route.query.branch === 'string' ? route.query.branch : '')

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logEntries.value = [...logEntries.value.slice(-49), createLogEntry(message, level)]
}

watch(
  () => route.query.actor,
  (a) => {
    if (a === 'main' || a === 'avatar') {
      craftStore.actor = a as CraftActor
    }
  },
  { immediate: true },
)

async function refreshAll(): Promise<void> {
  await Promise.all([craftStore.refreshJobs(), inventoryStore.load(), characterStore.fetchMe()])
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
  const err = await craftStore.load()
  if (err) loadError.value = err
  await inventoryStore.load()
  craftStore.startTick()
})

onUnmounted(() => {
  craftStore.stopTick()
})
</script>

<template>
  <div class="workshop-page">
    <AuthSessionBar />

    <div class="page-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-text tag="b" size="large">工坊</el-text>
      <el-text type="info" size="small">M4 · 配方队列 · M5 天气锁</el-text>
    </div>

    <CraftEnvHint />
    <CraftDaoUsageLine v-model="craftStore.useDao" />

    <div class="toolbar">
      <el-radio-group v-model="craftStore.actor" size="small">
        <el-radio-button value="main">本体队列</el-radio-button>
        <el-radio-button value="avatar">化身队列</el-radio-button>
      </el-radio-group>
      <StaminaBar class="stamina" />
    </div>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
      class="page-alert"
    />

    <CraftClaimBar @log="pushLog" @claimed="refreshAll" />

    <div class="workshop-grid">
      <RecipeList
        :initial-branch="initialBranch"
        @log="pushLog"
        @started="refreshAll"
      />
      <CraftJobQueue />
      <InventoryPanel />
    </div>
  </div>
</template>

<style scoped>
.workshop-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 1rem 1rem 2rem;
}

.page-title {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  margin: 0.75rem 0 1rem;
  flex-wrap: wrap;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}

.stamina {
  flex: 1;
  min-width: 200px;
}

.page-alert {
  margin-bottom: 1rem;
}

.workshop-grid {
  display: grid;
  grid-template-columns: 1fr 1fr minmax(200px, 260px);
  gap: 1rem;
  align-items: start;
}

@media (max-width: 900px) {
  .workshop-grid {
    grid-template-columns: 1fr;
  }
}
</style>
