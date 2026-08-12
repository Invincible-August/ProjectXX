<script setup lang="ts">
/**
 * 进阶栏：修为突破 / 淬体 同一卡片内切换。
 * 修为突破：同步结算弹结果；淬体：炼体境晋级。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  attemptBreakthroughApi,
  fetchBreakthroughChannelApi,
  fetchGradeHistoryApi,
  previewBreakthroughApi,
  resolveBreakthroughChannelApi,
} from '../api/breakthrough'
import {
  attemptQuenchApi,
  previewQuenchApi,
  type QuenchPreview,
} from '../api/quench'
import { startPrep } from '../api/tribulation'
import { useActivityGate } from '../composables/useActivityGate'
import { useCharacterStore } from '../stores/character'
import type {
  BreakthroughAttemptResult,
  BreakthroughPreview,
  GradeHistoryItem,
} from '../types/breakthrough'
import BreakthroughResultDialog from './BreakthroughResultDialog.vue'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const router = useRouter()
const characterStore = useCharacterStore()
const { canBreakthrough, canQuench, blockReason } = useActivityGate()

/** 栏内切换：修为突破 | 淬体 */
const mode = ref<'breakthrough' | 'quench'>('breakthrough')

const preview = ref<BreakthroughPreview | null>(null)
const quenchPreview = ref<QuenchPreview | null>(null)
const loadingPreview = ref(false)
const attempting = ref(false)
const resultVisible = ref(false)
const lastResult = ref<BreakthroughAttemptResult | null>(null)
const gradeHistory = ref<GradeHistoryItem[]>([])
const historyOpen = ref(false)
const needsTribulation = ref(false)
const startingPrep = ref(false)

let previewTimer: ReturnType<typeof setTimeout> | null = null
let previewSeq = 0

/**
 * 拉取跨境品阶历史。
 */
async function loadGradeHistory(): Promise<void> {
  try {
    const envelope = await fetchGradeHistoryApi()
    if (envelope.code === 0 && envelope.data?.items) {
      gradeHistory.value = envelope.data.items
    }
  } catch {
    // 历史失败不阻断突破主流程
  }
}

onMounted(() => {
  void loadGradeHistory()
  void recoverLegacyChannelIfNeeded()
})

onBeforeUnmount(() => {
  if (previewTimer !== null) {
    clearTimeout(previewTimer)
  }
})

/**
 * 应用结算结果弹窗。
 */
function applyResolvedResult(result: BreakthroughAttemptResult): void {
  lastResult.value = result
  if (result.character) {
    characterStore.applyCharacter(result.character)
  }
  resultVisible.value = true
  emit('log', result.message, result.success ? 'success' : 'warning')
  if (result.grade) {
    void loadGradeHistory()
  }
}

/**
 * 旧异步读条残留：刷新或 resolve 一次。
 */
async function recoverLegacyChannelIfNeeded(): Promise<void> {
  if (characterStore.character?.status !== 'breaking_through') return
  try {
    const resolved = await resolveBreakthroughChannelApi()
    if (resolved.code === 0 && resolved.data && resolved.data.success !== null) {
      applyResolvedResult(resolved.data)
      void refreshBreakthroughPreview(true)
      return
    }
    const ch = await fetchBreakthroughChannelApi()
    if (ch.code === 0 && ch.data?.character) {
      characterStore.applyCharacter(ch.data.character)
    }
    if (ch.data?.channel?.state === 'resolved' && ch.data.channel.result) {
      applyResolvedResult(ch.data.channel.result)
    }
  } catch {
    // 忽略
  }
}

/**
 * 拉取修为突破预览。
 */
async function refreshBreakthroughPreview(silent = false): Promise<void> {
  if (attempting.value) return
  const seq = ++previewSeq
  loadingPreview.value = true
  try {
    const envelope = await previewBreakthroughApi()
    if (seq !== previewSeq) return
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || '预览失败')
    }
    preview.value = envelope.data
    if (envelope.data.just_resolved && envelope.data.resolved_result) {
      applyResolvedResult(envelope.data.resolved_result)
    }
  } catch (e: unknown) {
    if (seq !== previewSeq) return
    const message = e instanceof Error ? e.message : '突破预览失败'
    if (!silent) {
      ElMessage.error(message)
      emit('log', message, 'warning')
    }
  } finally {
    if (seq === previewSeq) {
      loadingPreview.value = false
    }
  }
}

/**
 * 拉取淬体预览。
 */
async function refreshQuenchPreview(silent = false): Promise<void> {
  if (attempting.value) return
  const seq = ++previewSeq
  loadingPreview.value = true
  try {
    const envelope = await previewQuenchApi()
    if (seq !== previewSeq) return
    if (envelope.code !== 0 || !envelope.data) {
      if (!silent) {
        ElMessage.error(envelope.message || '淬体预览失败')
      }
      return
    }
    quenchPreview.value = envelope.data
    if (envelope.data.character) {
      characterStore.applyCharacter(envelope.data.character)
    }
  } catch (e: unknown) {
    if (!silent) {
      const message = e instanceof Error ? e.message : '淬体预览失败'
      ElMessage.error(message)
    }
  } finally {
    if (seq === previewSeq) loadingPreview.value = false
  }
}

function schedulePreviewRefresh(): void {
  if (previewTimer !== null) {
    clearTimeout(previewTimer)
  }
  previewTimer = setTimeout(() => {
    previewTimer = null
    if (mode.value === 'quench') {
      void refreshQuenchPreview(true)
    } else {
      void refreshBreakthroughPreview(true)
    }
  }, 280)
}

watch(mode, () => {
  schedulePreviewRefresh()
})

watch(
  () => {
    const ch = characterStore.character
    if (!ch) return ''
    return [
      ch.id,
      ch.realm_progress,
      ch.cultivation_points,
      ch.body_tempering_points,
      ch.body_temper_progress,
      ch.body_temper_stage,
      ch.spirit_stones,
      ch.major_realm,
      ch.realm_stage,
      ch.status,
      ch.last_settled_at,
      ch.offline_pending ? '1' : '0',
      mode.value,
    ].join('|')
  },
  (key) => {
    if (!key) {
      preview.value = null
      quenchPreview.value = null
      return
    }
    schedulePreviewRefresh()
  },
  { immediate: true },
)

/**
 * 处理雷劫分流。
 */
async function handleTribulationDivert(data: BreakthroughAttemptResult): Promise<void> {
  needsTribulation.value = true
  emit('log', data.message || '突破引发雷劫，请前往渡劫准备', 'warning')
  ElMessage.warning('本次进阶需渡劫')
  startingPrep.value = true
  try {
    const prep = await startPrep()
    if (prep.code === 0 && prep.data?.character) {
      characterStore.applyCharacter(prep.data.character)
    }
    await router.push('/tribulation')
  } catch {
    // start-prep 失败时保留 CTA
  } finally {
    startingPrep.value = false
  }
}

/**
 * 发起修为突破。
 */
async function onBreakthroughAttempt(): Promise<void> {
  if (attempting.value) return
  if (!canBreakthrough.value) {
    const msg = blockReason('breakthrough') || '修炼中不可突破，请先停止修炼'
    ElMessage.warning(msg)
    emit('log', msg, 'warning')
    return
  }
  attempting.value = true
  needsTribulation.value = false
  try {
    const envelope = await attemptBreakthroughApi()
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || `突破失败（code=${envelope.code}）`)
    }
    characterStore.applyCharacter(envelope.data.character)
    if (envelope.data.needs_tribulation) {
      await handleTribulationDivert(envelope.data)
      return
    }
    applyResolvedResult(envelope.data)
    void refreshBreakthroughPreview(true)
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '突破请求失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    attempting.value = false
  }
}

/**
 * 发起淬体。
 */
async function onQuenchAttempt(): Promise<void> {
  if (attempting.value) return
  if (!canQuench.value) {
    const msg = blockReason('quench') || '修炼中不可淬体，请先停止修炼'
    ElMessage.warning(msg)
    emit('log', msg, 'warning')
    return
  }
  attempting.value = true
  try {
    const envelope = await attemptQuenchApi()
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || `淬体失败（code=${envelope.code}）`)
    }
    characterStore.applyCharacter(envelope.data.character)
    if (envelope.data.success) {
      ElMessage.success(envelope.data.message)
      emit('log', envelope.data.message, 'success')
    } else {
      ElMessage.warning(envelope.data.message)
      emit('log', envelope.data.message, 'warning')
    }
    void refreshQuenchPreview(true)
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '淬体请求失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    attempting.value = false
  }
}

async function goTribulation(): Promise<void> {
  startingPrep.value = true
  try {
    const prep = await startPrep()
    if (prep.code === 0 && prep.data?.character) {
      characterStore.applyCharacter(prep.data.character)
    }
  } catch {
    // 已有会话时直接进页
  } finally {
    startingPrep.value = false
  }
  await router.push('/tribulation')
}
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="bt-header">
        <el-text tag="b">进阶</el-text>
        <el-text v-if="loadingPreview" type="info" size="small">同步中…</el-text>
      </div>
    </template>

    <el-radio-group v-model="mode" size="small" class="bt-mode">
      <el-radio-button value="breakthrough">修为突破</el-radio-button>
      <el-radio-button value="quench">淬体</el-radio-button>
    </el-radio-group>

    <!-- 修为突破 -->
    <template v-if="mode === 'breakthrough'">
      <template v-if="preview">
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="当前">
            {{ characterStore.character?.realm_display || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="成功后到达">
            {{ preview.next_realm_display || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="进阶方式">
            {{
              preview.advance_type_label_zh
                || (preview.advance_type === 'major'
                  ? '跨入下一大境'
                  : preview.advance_type === 'layer'
                    ? '同境升层/升期'
                    : preview.advance_type || '—')
            }}
          </el-descriptions-item>
          <el-descriptions-item label="境界进度">
            {{ preview.current_cultivation }} / {{ preview.required_cultivation }}
          </el-descriptions-item>
          <el-descriptions-item label="灵石消耗">
            {{ preview.spirit_stone_cost }}
          </el-descriptions-item>
          <el-descriptions-item label="成功率">
            {{ Math.round(preview.success_rate * 100) }}%
          </el-descriptions-item>
          <el-descriptions-item v-if="preview.grade_preview" label="品阶">
            {{ preview.grade_preview }}
          </el-descriptions-item>
        </el-descriptions>

        <el-text
          v-if="!preview.can_attempt && preview.reason"
          type="warning"
          size="small"
          class="bt-reason"
        >
          {{ preview.reason }}
        </el-text>

        <el-button
          class="bt-btn"
          type="warning"
          :disabled="!preview.can_attempt || attempting || !canBreakthrough"
          :loading="attempting"
          @click="onBreakthroughAttempt"
        >
          发起突破
        </el-button>

        <el-alert
          v-if="needsTribulation"
          title="本次进阶需渡雷劫"
          type="warning"
          show-icon
          :closable="false"
          class="bt-tribulation"
        >
          <el-button
            type="danger"
            size="small"
            :loading="startingPrep"
            @click="goTribulation"
          >
            前往渡劫准备
          </el-button>
        </el-alert>
      </template>
      <el-skeleton v-else animated :rows="4" />

      <div class="bt-history">
        <el-button
          text
          type="primary"
          size="small"
          @click="historyOpen = !historyOpen"
        >
          {{ historyOpen ? '收起' : '展开' }}品阶历史
          <template v-if="gradeHistory.length">（{{ gradeHistory.length }}）</template>
        </el-button>
        <el-timeline v-if="historyOpen && gradeHistory.length" class="bt-timeline">
          <el-timeline-item
            v-for="(item, index) in gradeHistory"
            :key="`${item.created_at}-${index}`"
            :timestamp="item.created_at"
            placement="top"
          >
            {{ item.from_realm_display }} → {{ item.to_realm_display }}：
            {{ item.grade_name || item.grade }}
          </el-timeline-item>
        </el-timeline>
        <el-text
          v-else-if="historyOpen && !gradeHistory.length"
          size="small"
          type="info"
        >
          尚无跨境品阶记录
        </el-text>
      </div>
    </template>

    <!-- 淬体 -->
    <template v-else>
      <template v-if="quenchPreview">
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="当前">
            {{ quenchPreview.from_display || quenchPreview.from_stage_name || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="成功后到达">
            {{ quenchPreview.to_display || quenchPreview.to_stage_name || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="进阶方式">
            {{
              quenchPreview.advance_type_label_zh
                || (quenchPreview.advance_type === 'major'
                  ? '跨入下一炼体境'
                  : quenchPreview.advance_type === 'layer'
                    ? '同境升层/升期'
                    : quenchPreview.advance_type || '—')
            }}
          </el-descriptions-item>
          <el-descriptions-item label="淬体进度">
            {{ quenchPreview.progress }} / {{ quenchPreview.required }}
          </el-descriptions-item>
          <el-descriptions-item
            v-if="quenchPreview.success_rate != null"
            label="成功率"
          >
            {{ Math.round((quenchPreview.success_rate || 0) * 100) }}%
          </el-descriptions-item>
        </el-descriptions>

        <el-text size="small" type="info" class="bt-reason">
          淬体不渡劫；失败会回退部分淬体进度。
        </el-text>

        <el-text
          v-if="!quenchPreview.can_quench && quenchPreview.reason"
          type="warning"
          size="small"
          class="bt-reason"
        >
          {{ quenchPreview.reason }}
        </el-text>

        <el-button
          class="bt-btn"
          type="success"
          :disabled="!quenchPreview.can_quench || attempting || !canQuench"
          :loading="attempting"
          @click="onQuenchAttempt"
        >
          发起淬体
        </el-button>
      </template>
      <el-skeleton v-else animated :rows="3" />
    </template>

    <BreakthroughResultDialog
      v-model:visible="resultVisible"
      :result="lastResult"
    />
  </el-card>
</template>

<style scoped>
.bt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.bt-mode {
  margin-bottom: 0.75rem;
  width: 100%;
}

.bt-mode :deep(.el-radio-button) {
  flex: 1;
}

.bt-mode :deep(.el-radio-button__inner) {
  width: 100%;
}

.bt-reason {
  display: block;
  margin: 0.5rem 0;
}

.bt-btn {
  margin-top: 0.75rem;
  width: 100%;
}

.bt-tribulation {
  margin-top: 0.75rem;
}

.bt-history {
  margin-top: 1rem;
}

.bt-timeline {
  margin-top: 0.5rem;
  padding-left: 0.25rem;
}
</style>
