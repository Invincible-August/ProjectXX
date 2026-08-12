<script setup lang="ts">
/**
 * 灵兽园页（M4 · /pets）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import PetCatalogPanel from '../components/pets/PetCatalogPanel.vue'
import PetDetailPanel from '../components/pets/PetDetailPanel.vue'
import PetDuelPanel from '../components/pets/PetDuelPanel.vue'
import PetExplorePanel from '../components/pets/PetExplorePanel.vue'
import PetHatchPanel from '../components/pets/PetHatchPanel.vue'
import PetList from '../components/pets/PetList.vue'
import { useCharacterStore } from '../stores/character'
import { usePetsStore } from '../stores/pets'
import type { PetPublic } from '../types/pets'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'

const route = useRoute()
const router = useRouter()
const petsStore = usePetsStore()
const characterStore = useCharacterStore()

const loadError = ref('')
const captureBusy = ref(false)
const isDev = import.meta.env.DEV
const selected = ref<PetPublic | null>(null)
const logEntries = ref<GameLogEntry[]>([])
const activeTab = ref<'owned' | 'dex' | 'hatch' | 'duel' | 'explore'>('owned')

const focusId = computed(() => {
  const raw = route.query.focus
  const n = Number(raw)
  return Number.isInteger(n) ? n : null
})

const holdLabel = computed(() => {
  const n = petsStore.pets.length
  return `持有 ${n}/${petsStore.cap}`
})

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logEntries.value = [...logEntries.value.slice(-49), createLogEntry(message, level)]
}

function selectPet(pet: PetPublic): void {
  selected.value = pet
}

watch(
  () => petsStore.pets,
  (list) => {
    if (focusId.value != null) {
      selected.value = list.find((p) => p.id === focusId.value) ?? selected.value
    } else if (selected.value) {
      selected.value = list.find((p) => p.id === selected.value!.id) ?? null
    }
  },
)

async function onCaptureTest(): Promise<void> {
  if (captureBusy.value) return
  captureBusy.value = true
  try {
    const error = await petsStore.captureTest()
    if (error) {
      ElMessage.error(error)
      pushLog(error, 'warning')
      return
    }
    ElMessage.success('测试捕获成功（物种表加权抽取）')
    pushLog('测试捕获（非正式野外 · 物种表抽取）', 'success')
    await characterStore.fetchMe()
    if (petsStore.pets.length > 0) {
      selected.value = petsStore.pets[petsStore.pets.length - 1]
    }
  } finally {
    captureBusy.value = false
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
  const err = await petsStore.load()
  if (err) loadError.value = err
  const catalogErr = await petsStore.loadCatalog()
  if (catalogErr && !loadError.value) loadError.value = catalogErr
  if (focusId.value != null) {
    selected.value = petsStore.pets.find((p) => p.id === focusId.value) ?? null
  } else if (petsStore.pets.length > 0) {
    selected.value = petsStore.pets[0]
  }
})
</script>

<template>
  <div class="pets-page">
    <AuthSessionBar />

    <div class="page-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-text tag="b" size="large">灵兽园</el-text>
      <el-text type="info" size="small">{{ holdLabel }}</el-text>
      <el-button
        v-if="isDev"
        size="small"
        type="warning"
        :loading="captureBusy"
        @click="onCaptureTest"
      >
        测试捕获（物种表抽取）
      </el-button>
    </div>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
      class="page-alert"
    />

    <el-tabs v-model="activeTab" class="pets-tabs">
      <el-tab-pane label="持有" name="owned">
        <div class="pets-grid">
          <PetList :pets="petsStore.pets" :focus-id="focusId" @select="selectPet" />
          <PetDetailPanel :pet="selected" @log="pushLog" />
        </div>
      </el-tab-pane>
      <el-tab-pane label="图鉴" name="dex">
        <PetCatalogPanel :species="petsStore.catalog?.species ?? []" />
      </el-tab-pane>
      <el-tab-pane label="孵化" name="hatch">
        <PetHatchPanel @log="pushLog" />
      </el-tab-pane>
      <el-tab-pane label="野外" name="explore">
        <PetExplorePanel @log="pushLog" />
      </el-tab-pane>
      <el-tab-pane label="对战" name="duel">
        <PetDuelPanel :pets="petsStore.pets" @log="pushLog" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.pets-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 1rem 1rem 2rem;
}

.page-title {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.75rem;
  margin: 0.75rem 0 1rem;
}

.page-alert {
  margin-bottom: 1rem;
}

.pets-tabs {
  margin-top: 0.25rem;
}

.pets-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  align-items: start;
}

@media (max-width: 700px) {
  .pets-grid {
    grid-template-columns: 1fr;
  }
}
</style>
