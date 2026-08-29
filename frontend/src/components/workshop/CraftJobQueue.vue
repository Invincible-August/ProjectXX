<script setup lang="ts">
/**
 * 工坊队列：顺序排队进度 + 取消。
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useCraftStore } from '../../stores/craft'
import { useInventoryStore } from '../../stores/inventory'
import { useCharacterStore } from '../../stores/character'
import type { CraftJob } from '../../types/craft'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
  changed: []
}>()

const craftStore = useCraftStore()
const inventoryStore = useInventoryStore()
const characterStore = useCharacterStore()
const busyId = ref<number | null>(null)

const recipeName = (recipeId: string): string =>
  craftStore.recipes.find((r) => r.recipe_id === recipeId)?.name ?? recipeId

/** 按完成时刻升序：先完成的在上 */
const sortedJobs = computed(() =>
  [...craftStore.jobs]
    .filter((j) => j.status === 'running' || j.status === 'claimed' || j.status === 'failed')
    .sort((a, b) => {
      const ta = Date.parse(a.finish_at) || 0
      const tb = Date.parse(b.finish_at) || 0
      if (ta !== tb) return ta - tb
      return a.id - b.id
    }),
)

function progressOf(job: CraftJob): number {
  if (job.status !== 'running') return 100
  return Math.round((craftStore.localProgress[job.id] ?? 0) * 100)
}

const statusLabel: Record<string, string> = {
  running: '制造中',
  claimed: '已入包',
  failed: '失败',
  cancelled: '已取消',
  ready: '已入包',
}

function isActivelyCrafting(job: CraftJob): boolean {
  if (job.status !== 'running') return false
  const started = Date.parse(job.started_at)
  if (!Number.isFinite(started)) return false
  return started <= Date.now()
}

async function onCancel(job: CraftJob): Promise<void> {
  if (job.status !== 'running' || busyId.value != null) return
  busyId.value = job.id
  try {
    const error = await craftStore.cancel(job.id)
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    ElMessage.success('已取消并退回冻结资源')
    emit('log', `取消制造：${recipeName(job.recipe_id)}`, 'info')
    await inventoryStore.load()
    await characterStore.fetchMe()
    emit('changed')
  } finally {
    busyId.value = null
  }
}
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">队列（{{ craftStore.runningJobs.length }} 排队）</el-text>
    </template>

    <el-empty v-if="sortedJobs.length === 0" description="暂无工坊任务" :image-size="48" />

    <div v-for="job in sortedJobs" :key="job.id" class="job-item">
      <div class="job-head">
        <el-text tag="b" size="small">
          {{ recipeName(job.recipe_id) }}
          <el-text v-if="(job.quantity ?? 1) > 1" size="small" type="info">
            ×{{ job.quantity }}
          </el-text>
        </el-text>
        <el-tag
          size="small"
          :type="job.status === 'claimed' ? 'success' : job.status === 'failed' ? 'danger' : 'info'"
        >
          {{
            job.status === 'running'
              ? isActivelyCrafting(job)
                ? '制造中'
                : '排队中'
              : statusLabel[job.status] ?? job.status
          }}
        </el-tag>
        <el-text size="small" type="info">{{ job.actor === 'main' ? '本体' : '化身' }}</el-text>
        <el-button
          v-if="job.status === 'running'"
          size="small"
          type="danger"
          plain
          :loading="busyId === job.id"
          :disabled="busyId != null && busyId !== job.id"
          @click="onCancel(job)"
        >
          取消
        </el-button>
      </div>
      <el-progress
        v-if="job.status === 'running'"
        :percentage="progressOf(job)"
        striped
        striped-flow
        class="job-progress"
      />
    </div>
  </el-card>
</template>

<style scoped>
.job-item {
  margin-bottom: 0.75rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}

.job-item:last-child {
  border-bottom: none;
}

.job-head {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: center;
  margin-bottom: 0.25rem;
}

.job-progress {
  margin-top: 0.25rem;
}
</style>
