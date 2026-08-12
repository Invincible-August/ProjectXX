<script setup lang="ts">
/**
 * 渡劫页（M5 · /tribulation）：准备 → 开渡结算。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import TribulationCloudBanner from '../components/tribulation/TribulationCloudBanner.vue'
import TribulationPrepBoard from '../components/tribulation/TribulationPrepBoard.vue'
import TribulationResolvePanel from '../components/tribulation/TribulationResolvePanel.vue'
import TribulationResultDialog from '../components/tribulation/TribulationResultDialog.vue'
import TribulationStatusPanel from '../components/tribulation/TribulationStatusPanel.vue'
import TribulationVeilPanel from '../components/tribulation/TribulationVeilPanel.vue'
import { useCharacterStore } from '../stores/character'
import { useTribulationStore } from '../stores/tribulation'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'

const route = useRoute()
const router = useRouter()
const characterStore = useCharacterStore()
const tribulationStore = useTribulationStore()

const loadError = ref('')
const logEntries = ref<GameLogEntry[]>([])
const resultVisible = ref(false)
const beginning = ref(false)

const session = computed(() => tribulationStore.session)
const showPrep = computed(
  () =>
    session.value &&
    (session.value.phase === 'preparing' || session.value.phase === 'committed'),
)
const showResolve = computed(() => session.value?.phase === 'running')
/** 进度 100% / 终局：页内可直接点「确认突破」 */
const showFinished = computed(() => {
  const p = session.value?.phase
  return p === 'won' || p === 'failed' || p === 'fallen'
})
const isWon = computed(() => session.value?.phase === 'won')

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logEntries.value = [...logEntries.value.slice(-49), createLogEntry(message, level)]
}

async function onBegin(): Promise<void> {
  if (beginning.value) return
  beginning.value = true
  try {
    const err = await tribulationStore.begin()
    if (err) throw new Error(err)
    ElMessage.success('开渡成功，劫云已覆盖；准备格道具已从背包消耗')
    pushLog('开渡：准备格道具已消耗，进入雷劫结算', 'success')
    // 开渡后刷新背包，避免界面仍显示已消耗道具
    void import('../stores/inventory').then(({ useInventoryStore }) => {
      void useInventoryStore().load()
    })
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '开渡失败'
    ElMessage.error(message)
    pushLog(message, 'warning')
  } finally {
    beginning.value = false
  }
}

function onFinished(): void {
  resultVisible.value = true
  if (session.value?.phase === 'fallen') {
    pushLog('陨落：进入待引渡', 'warning')
  } else if (session.value?.phase === 'won') {
    pushLog('渡劫圆满：可点击「确认突破」返回大厅', 'success')
  }
  // 兜底同步角色态（后端应已在 outcome 带回 character）
  void characterStore.fetchMe()
}

/** 页内主按钮：确认突破（成功）或打开结果说明 */
function onConfirmBreakthrough(): void {
  resultVisible.value = true
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
  const err = await tribulationStore.load()
  if (err) {
    loadError.value = err
    pushLog(err, 'warning')
  } else if (!tribulationStore.session) {
    pushLog('当前无需渡劫；仅跨大境界（元婴→化神起）会引发雷劫，小境界可直接突破。', 'info')
  } else {
    pushLog(
      `本次雷劫：${tribulationStore.session.power_label} · ${tribulationStore.session.count_label}`,
      'info',
    )
    // ?wave= 只读意图：高亮日志
    if (route.query.wave) {
      pushLog(`意图高亮波次：${route.query.wave}`, 'system')
    }
  }
})
</script>

<template>
  <div class="tribulation-page">
    <AuthSessionBar />

    <div class="page-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-text tag="b" size="large">渡劫</el-text>
      <el-text type="info" size="small">M5 · 准备 / 结算</el-text>
    </div>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
      class="page-alert"
    />

    <el-empty
      v-if="!session && !tribulationStore.loading"
      description="当前无需渡劫；仅跨大境界（元婴→化神起）会引发雷劫，小境界进阶可直接突破"
    >
      <el-button type="primary" @click="router.push('/hall')">回大厅</el-button>
    </el-empty>

    <template v-else-if="session">
      <TribulationCloudBanner :session="session" />
      <TribulationStatusPanel :session="session" />

      <div v-if="showPrep" class="prep-grid">
        <TribulationPrepBoard @log="pushLog" />
        <div class="prep-side">
          <TribulationVeilPanel @log="pushLog" />
          <el-card shadow="never">
            <el-text size="small" type="info">
              气运 {{ characterStore.character?.fate_luck ?? session.fate_luck ?? '—' }}
              · 魔性
              {{ characterStore.character?.demonic_nature ?? session.demonic_nature ?? '—' }}
            </el-text>
            <el-button
              class="begin-btn"
              type="danger"
              :disabled="session.phase !== 'committed'"
              :loading="beginning"
              @click="onBegin"
            >
              开渡（消耗准备格道具）
            </el-button>
            <el-text
              v-if="session.phase === 'preparing'"
              size="small"
              type="warning"
              class="begin-tip"
            >
              请先确认准备
            </el-text>
            <el-text
              v-else-if="session.phase === 'committed'"
              size="small"
              type="warning"
              class="begin-tip"
            >
              开渡后准备格内道具将永久从背包扣除
            </el-text>
          </el-card>
        </div>
      </div>

      <TribulationResolvePanel
        v-if="showResolve"
        @log="pushLog"
        @finished="onFinished"
      />

      <el-card v-if="showFinished" shadow="never" class="finish-card">
        <template #header>
          <el-text tag="b">
            {{ isWon ? '渡劫圆满' : session?.phase === 'fallen' ? '陨落' : '渡劫结束' }}
          </el-text>
        </template>
        <el-text v-if="isWon" size="small">
          雷劫进度已达 100%，境界进阶已生效（{{ session?.target_label || '—' }}）。
          可在本页直接确认突破。
        </el-text>
        <el-text v-else-if="session?.phase === 'fallen'" size="small" type="warning">
          已进入待引渡，请前往轮回与引渡页。
        </el-text>
        <el-text v-else size="small">渡劫已结束，可查看结果或返回大厅。</el-text>
        <div class="finish-actions">
          <el-button v-if="isWon" type="primary" @click="onConfirmBreakthrough">
            确认突破
          </el-button>
          <el-button
            v-else-if="session?.phase === 'fallen'"
            type="warning"
            @click="router.push({ name: 'reincarnation', query: { mode: 'ferry' } })"
          >
            前往轮回与引渡
          </el-button>
          <el-button v-else type="primary" @click="resultVisible = true">查看结果</el-button>
          <el-button @click="router.push('/hall')">回大厅</el-button>
        </div>
      </el-card>

      <TribulationResultDialog
        v-model:visible="resultVisible"
        :session="session"
      />
    </template>

    <el-card v-if="logEntries.length" shadow="never" class="page-log">
      <template #header>
        <el-text tag="b" size="small">本页日志</el-text>
      </template>
      <div v-for="entry in logEntries" :key="entry.id" class="log-line">
        <el-text size="small">{{ entry.message }}</el-text>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.tribulation-page {
  max-width: 1000px;
  margin: 0 auto;
  padding: 1rem 1rem 2rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.page-title {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.page-alert {
  margin-bottom: 0.25rem;
}

.prep-grid {
  display: grid;
  grid-template-columns: 1fr minmax(200px, 280px);
  gap: 0.75rem;
  align-items: start;
}

.prep-side {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.begin-btn {
  width: 100%;
  margin-top: 0.75rem;
}

.begin-tip {
  display: block;
  margin-top: 0.35rem;
}

.finish-card {
  margin-top: 0.25rem;
}

.finish-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.page-log {
  margin-top: 0.5rem;
}

.log-line {
  margin-bottom: 0.2rem;
}

@media (max-width: 800px) {
  .prep-grid {
    grid-template-columns: 1fr;
  }
}
</style>
