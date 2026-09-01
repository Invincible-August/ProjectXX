<script setup lang="ts">
/**
 * 研究室（洞府二级页）：功法 / 阵盘 / 符箓图纸。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import TechniqueResearchPanel from '../components/research/TechniqueResearchPanel.vue'
import FormationResearchPanel from '../components/research/FormationResearchPanel.vue'
import TalismanResearchPanel from '../components/research/TalismanResearchPanel.vue'
import ResearchMineList from '../components/research/ResearchMineList.vue'
import { usePlayWriteGate } from '../composables/usePlayWriteGate'
import { CAVE_LAB_PATH } from '../constants/cave'
import { useCharacterStore } from '../stores/character'
import { useResearchStore } from '../stores/research'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'

type ResearchMode = 'technique' | 'formation' | 'talisman'

const MODE_SET = new Set<string>(['technique', 'formation', 'talisman'])

const route = useRoute()
const router = useRouter()
const characterStore = useCharacterStore()
const researchStore = useResearchStore()
const { writeBlocked, writeBlockReason } = usePlayWriteGate()

const loadError = ref('')
const logEntries = ref<GameLogEntry[]>([])

const mode = computed<ResearchMode>(() => {
  const m = route.query.mode
  if (typeof m === 'string' && MODE_SET.has(m)) {
    return m as ResearchMode
  }
  return 'technique'
})

async function setMode(next: ResearchMode): Promise<void> {
  if (next === mode.value) return
  if (researchStore.hasUnsavedFormationDraft) {
    try {
      await ElMessageBox.confirm('阵法草案未保存，切换分支将丢弃未保存绘制。确定切换？', '未保存', {
        confirmButtonText: '放弃修改',
        cancelButtonText: '留下',
      })
    } catch {
      return
    }
  }
  researchStore.clearSession()
  void router.replace({ path: CAVE_LAB_PATH, query: { mode: next } })
}

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logEntries.value = [...logEntries.value.slice(-49), createLogEntry(message, level)]
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
  const catalogErr = await researchStore.loadCatalog()
  if (catalogErr) {
    loadError.value = catalogErr
  }
  const mineErr = await researchStore.loadMine()
  if (mineErr && !loadError.value) {
    loadError.value = mineErr
  }
  const sessionRaw = route.query.session
  const sessionId = typeof sessionRaw === 'string' ? Number(sessionRaw) : NaN
  if (Number.isFinite(sessionId) && sessionId > 0) {
    const sessErr = await researchStore.loadSession(sessionId)
    if (sessErr) {
      loadError.value = sessErr
    } else if (researchStore.session?.kind) {
      const kind = researchStore.session.kind
      if (MODE_SET.has(kind) && mode.value !== kind) {
        void router.replace({
          path: CAVE_LAB_PATH,
          query: { mode: kind, session: String(sessionId) },
        })
      }
    }
  }
})

watch(mode, () => {
  loadError.value = ''
})
</script>

<template>
  <div class="lab-page">
    <div class="mode-nav">
      <el-button
        size="small"
        :type="mode === 'technique' ? 'primary' : 'default'"
        @click="setMode('technique')"
      >
        功法
      </el-button>
      <el-button
        size="small"
        :type="mode === 'formation' ? 'primary' : 'default'"
        @click="setMode('formation')"
      >
        阵法
      </el-button>
      <el-button
        size="small"
        :type="mode === 'talisman' ? 'primary' : 'default'"
        @click="setMode('talisman')"
      >
        符箓
      </el-button>
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

    <div class="main-grid" :class="{ 'main-grid-wide': mode === 'technique' }">
      <div class="main-left">
        <TechniqueResearchPanel v-if="mode === 'technique'" @log="pushLog" />
        <FormationResearchPanel v-else-if="mode === 'formation'" @log="pushLog" />
        <TalismanResearchPanel v-else @log="pushLog" />
        <ResearchMineList v-if="mode !== 'technique'" :kind="mode" />
      </div>
      <aside v-if="mode !== 'technique'" class="main-side">
        <el-card v-if="logEntries.length" shadow="never">
          <template #header>
            <el-text tag="b" size="small">本页日志</el-text>
          </template>
          <el-text
            v-for="e in logEntries.slice(-12)"
            :key="e.id"
            size="small"
            class="log-line"
          >
            {{ e.message }}
          </el-text>
        </el-card>
      </aside>
    </div>
    <el-card
      v-if="mode === 'technique' && logEntries.length"
      shadow="never"
      class="tech-log"
    >
      <template #header>
        <el-text tag="b" size="small">本页日志</el-text>
      </template>
      <el-text
        v-for="e in logEntries.slice(-12)"
        :key="e.id"
        size="small"
        class="log-line"
      >
        {{ e.message }}
      </el-text>
    </el-card>
  </div>
</template>

<style scoped>
.mode-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.75rem;
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
.main-grid-wide {
  grid-template-columns: 1fr;
}
.main-left,
.main-side {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-width: 0;
}
.tech-log {
  margin-top: 0.75rem;
}
.log-line {
  display: block;
  padding: 0.15rem 0;
}
@media (max-width: 800px) {
  .main-grid {
    grid-template-columns: 1fr;
  }
}
</style>
