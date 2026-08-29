<script setup lang="ts">
/**
 * 工坊页（洞府二级 · /cave/workshop）：外层四分支 / 配方 / 队列。
 */
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StaminaBar from '../components/battle/StaminaBar.vue'
import CraftJobQueue from '../components/workshop/CraftJobQueue.vue'
import RecipeList from '../components/workshop/RecipeList.vue'
import { usePlayWriteGate } from '../composables/usePlayWriteGate'
import { CAVE_WORKSHOP_PATH } from '../constants/cave'
import { useCraftStore } from '../stores/craft'
import { useCharacterStore } from '../stores/character'
import { useInventoryStore } from '../stores/inventory'
import type { CraftActor, CraftBranch } from '../types/craft'
import { CRAFT_BRANCH_TABS } from '../types/craft'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'

const route = useRoute()
const router = useRouter()
const craftStore = useCraftStore()
const characterStore = useCharacterStore()
const inventoryStore = useInventoryStore()
const { writeBlocked, writeBlockReason } = usePlayWriteGate()

const loadError = ref('')
const logEntries = ref<GameLogEntry[]>([])

const BRANCH_KEYS = new Set<string>(CRAFT_BRANCH_TABS.map((tab) => tab.key))

function normalizeBranch(raw: unknown): CraftBranch {
  return typeof raw === 'string' && BRANCH_KEYS.has(raw) ? (raw as CraftBranch) : 'alchemy'
}

const workshopBranch = ref<CraftBranch>(normalizeBranch(route.query.branch))

function onBranchChange(next: CraftBranch): void {
  if (next === workshopBranch.value) return
  workshopBranch.value = next
  const query = { ...route.query, branch: next }
  void router.replace({ path: CAVE_WORKSHOP_PATH, query })
}

watch(
  () => route.query.branch,
  (b) => {
    workshopBranch.value = normalizeBranch(b)
  },
)

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
    <div class="mode-nav">
      <el-button
        v-for="tab in CRAFT_BRANCH_TABS"
        :key="tab.key"
        size="small"
        :type="workshopBranch === tab.key ? 'primary' : 'default'"
        @click="onBranchChange(tab.key)"
      >
        {{ tab.label }}
      </el-button>
    </div>

    <div class="toolbar">
      <el-radio-group v-model="craftStore.actor" size="small">
        <el-radio-button value="main">本体队列</el-radio-button>
        <el-radio-button value="avatar">化身队列</el-radio-button>
      </el-radio-group>
      <StaminaBar class="stamina" />
    </div>

    <el-alert
      v-if="writeBlocked"
      :title="writeBlockReason"
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
      :closable="false"
      class="page-alert"
    />

    <div class="workshop-grid">
      <RecipeList :branch="workshopBranch" @log="pushLog" @started="refreshAll" />
      <CraftJobQueue @log="pushLog" @changed="refreshAll" />
    </div>
  </div>
</template>

<style scoped>
.workshop-page {
  min-width: 0;
}

.mode-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.75rem;
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
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  align-items: start;
}

@media (max-width: 900px) {
  .workshop-grid {
    grid-template-columns: 1fr;
  }
}
</style>
