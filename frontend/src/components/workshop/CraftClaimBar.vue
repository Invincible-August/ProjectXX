<script setup lang="ts">
/**
 * 可领取任务快捷栏。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useCraftStore } from '../../stores/craft'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
  claimed: []
}>()

const craftStore = useCraftStore()
const busyId = ref<number | null>(null)

function recipeName(recipeId: string): string {
  return craftStore.recipes.find((r) => r.recipe_id === recipeId)?.name ?? recipeId
}

async function onClaim(jobId: number): Promise<void> {
  if (busyId.value != null) return
  busyId.value = jobId
  try {
    const { error, failed } = await craftStore.claim(jobId)
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    if (failed) {
      ElMessage.warning('炼制失败，材料已耗')
      emit('log', '工坊领取：炼制失败', 'warning')
    } else {
      ElMessage.success('领取成功')
      emit('log', `工坊领取 job#${jobId}`, 'success')
    }
    emit('claimed')
  } finally {
    busyId.value = null
  }
}
</script>

<template>
  <el-card v-if="craftStore.readyJobs.length > 0" shadow="never" class="claim-bar">
    <template #header>
      <el-text tag="b">可领取（{{ craftStore.readyJobs.length }}）</el-text>
    </template>
    <div class="claim-list">
      <div v-for="job in craftStore.readyJobs" :key="job.id" class="claim-item">
        <el-text size="small">{{ recipeName(job.recipe_id) }} #{{ job.id }}</el-text>
        <el-button
          size="small"
          type="success"
          :loading="busyId === job.id"
          @click="onClaim(job.id)"
        >
          领取
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.claim-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.claim-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
</style>
