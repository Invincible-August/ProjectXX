<script setup lang="ts">
/**
 * 工坊队列：running 本地进度条 + 列表。
 */
import { computed } from 'vue'
import { useCraftStore } from '../../stores/craft'
import type { CraftJob } from '../../types/craft'

const craftStore = useCraftStore()

const recipeName = (recipeId: string): string =>
  craftStore.recipes.find((r) => r.recipe_id === recipeId)?.name ?? recipeId

const sortedJobs = computed(() =>
  [...craftStore.jobs].sort((a, b) => b.id - a.id),
)

function progressOf(job: CraftJob): number {
  if (job.status === 'ready') return 100
  if (job.status !== 'running') return 0
  return Math.round((craftStore.localProgress[job.id] ?? 0) * 100)
}

const statusLabel: Record<string, string> = {
  running: '进行中',
  ready: '可领取',
  claimed: '已领取',
  failed: '失败',
}
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">队列（{{ craftStore.runningJobs.length }} 进行中）</el-text>
    </template>

    <el-empty v-if="sortedJobs.length === 0" description="暂无工坊任务" :image-size="48" />

    <div v-for="job in sortedJobs" :key="job.id" class="job-item">
      <div class="job-head">
        <el-text tag="b" size="small">{{ recipeName(job.recipe_id) }}</el-text>
        <el-tag size="small" :type="job.status === 'ready' ? 'success' : 'info'">
          {{ statusLabel[job.status] ?? job.status }}
        </el-tag>
        <el-text size="small" type="info">{{ job.actor === 'main' ? '本体' : '化身' }}</el-text>
        <el-text
          v-if="job.locked_weather_label || job.locked_weather"
          size="small"
          type="warning"
        >
          锁天气 {{ job.locked_weather_label || job.locked_weather }}
        </el-text>
      </div>
      <el-progress
        v-if="job.status === 'running' || job.status === 'ready'"
        :percentage="progressOf(job)"
        :status="job.status === 'ready' ? 'success' : undefined"
        striped
        :striped-flow="job.status === 'running'"
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
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.35rem;
}

.job-progress {
  transition: width 0.3s ease;
}
</style>
