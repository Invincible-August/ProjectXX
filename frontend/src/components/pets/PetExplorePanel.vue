<script setup lang="ts">
/**
 * M4-D04c 野外探索：遭遇 / 捕获 / 自动捕（占位区）。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { usePetsStore } from '../../stores/pets'
import { shichenLabel } from '../../utils/shichenLabel'
import { weatherLabel } from '../../utils/weatherIcon'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const petsStore = usePetsStore()
const busy = ref(false)
const loadError = ref('')
const regionId = ref('default')

const preview = computed(() => petsStore.explorePreview)
const encounter = computed(() => petsStore.lastEncounter)
const capture = computed(() => petsStore.lastCapture)

async function refreshPreview(): Promise<void> {
  const error = await petsStore.loadExplorePreview(regionId.value)
  if (error) {
    loadError.value = error
    return
  }
  loadError.value = ''
}

async function onEncounter(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const error = await petsStore.exploreEncounter(regionId.value)
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    const enc = petsStore.lastEncounter
    const msg = enc?.capturable
      ? `遭遇可捕：${enc.label || enc.species_id}（品阶 ${enc.grade}）`
      : `遭遇：${enc?.label || enc?.type || '未知'}（不可捕）`
    ElMessage.info(msg)
    emit('log', msg, 'info')
  } finally {
    busy.value = false
  }
}

async function onCapture(): Promise<void> {
  if (busy.value || !encounter.value?.capturable) return
  busy.value = true
  try {
    const error = await petsStore.exploreCapture()
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    const r = petsStore.lastCapture
    if (!r) return
    const audit = `p=${r.p.toFixed(3)} roll=${r.roll.toFixed(3)} seed=${r.seed}`
    if (r.success) {
      ElMessage.success(`捕获成功 · ${audit}`)
      emit('log', `野外捕获成功（wild_capture）· ${audit}`, 'success')
    } else {
      ElMessage.warning(`捕获失败 · ${audit}`)
      emit('log', `野外捕获失败 · ${audit}`, 'warning')
    }
  } finally {
    busy.value = false
  }
}

async function onAuto(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const error = await petsStore.exploreAuto(regionId.value)
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    const r = petsStore.lastCapture
    if (r?.success) {
      ElMessage.success('自动捕成功')
      emit('log', '自动探索捕获成功', 'success')
    } else if (r) {
      ElMessage.warning('自动捕尝试失败')
      emit('log', '自动探索捕获失败', 'warning')
    } else {
      ElMessage.info('本轮未遇到可捕或无草/袋')
      emit('log', '自动探索未触发捕获', 'info')
    }
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  void refreshPreview()
})
</script>

<template>
  <div class="explore-panel">
    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
      class="mb"
    />

    <el-text tag="b" size="small">野外探索（占位区 · 非正式地图）</el-text>
    <div class="row mb">
      <el-input v-model="regionId" size="small" style="max-width: 160px" placeholder="region_id" />
      <el-button size="small" :loading="busy" @click="refreshPreview">刷新环境</el-button>
      <el-button size="small" type="primary" :loading="busy" @click="onEncounter">遭遇</el-button>
      <el-button
        size="small"
        type="success"
        :disabled="!encounter?.capturable"
        :loading="busy"
        @click="onCapture"
      >
        捕获
      </el-button>
      <el-button
        size="small"
        type="warning"
        :disabled="!preview?.auto_capture_enabled"
        :loading="busy"
        @click="onAuto"
      >
        自动捕
      </el-button>
    </div>

    <el-descriptions v-if="preview" :column="2" size="small" border class="mb">
      <el-descriptions-item label="区域">
        {{ preview.region_label || preview.region_id }}
      </el-descriptions-item>
      <el-descriptions-item label="时辰">
        {{ shichenLabel(preview.shichen, preview.shichen_label) }}
      </el-descriptions-item>
      <el-descriptions-item label="天气">
        {{ weatherLabel(preview.weather, preview.weather_label) }}
      </el-descriptions-item>
      <el-descriptions-item label="诱灵草">
        {{ preview.lure_count }}（{{ preview.lure_item_id }}）
      </el-descriptions-item>
      <el-descriptions-item label="灵兽袋">
        {{ preview.bag_ok ? '有' : '无' }}
      </el-descriptions-item>
      <el-descriptions-item label="跳过战斗">
        {{ preview.skip_battle ? '是' : '否' }}
      </el-descriptions-item>
    </el-descriptions>

    <div v-if="encounter" class="block mb">
      <el-text tag="b" size="small">当前遭遇</el-text>
      <p class="muted">
        {{ encounter.label || encounter.type }} ·
        <template v-if="encounter.capturable">
          {{ encounter.species_name || encounter.species_id }} · 品阶 {{ encounter.grade }} · 特殊词条估
          {{ encounter.special_affix_count ?? 0 }}
        </template>
        <template v-else>不可捕</template>
      </p>
    </div>

    <div v-if="capture" class="block">
      <el-text tag="b" size="small">捕获审计</el-text>
      <pre class="audit">{{
        JSON.stringify(
          {
            success: capture.success,
            p: capture.p,
            roll: capture.roll,
            seed: capture.seed,
            factors: capture.factors,
            acquire_tag: capture.acquire_tag,
          },
          null,
          2,
        )
      }}</pre>
    </div>

    <el-text type="info" size="small">
      DEV 发材料含诱灵草与灵兽袋。路径独立于测试捕获（acquire_tag=wild_capture）。
    </el-text>
  </div>
</template>

<style scoped>
.explore-panel {
  padding: 0.25rem 0 1rem;
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  margin-top: 0.5rem;
}
.mb {
  margin-bottom: 0.75rem;
}
.block p {
  margin: 0.35rem 0 0;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 0.875rem;
}
.audit {
  margin: 0.35rem 0 0;
  padding: 0.5rem;
  font-size: 0.75rem;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  overflow: auto;
  max-height: 220px;
}
</style>
