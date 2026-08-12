<script setup lang="ts">
/**
 * N5 灵兽蛋孵化面板：选蛋开工 / 领取入园。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { usePetsStore } from '../../stores/pets'
import type { PetHatchEggPublic, PetHatchJobPublic } from '../../types/pets'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const petsStore = usePetsStore()
const busyEgg = ref<string | null>(null)
const busyJob = ref<number | null>(null)
const loadError = ref('')

const eggs = ref<PetHatchEggPublic[]>([])
const jobs = ref<PetHatchJobPublic[]>([])
const activeCount = ref(0)
const maxConcurrent = ref(0)

async function refresh(): Promise<void> {
  const error = await petsStore.loadHatch()
  if (error) {
    loadError.value = error
    return
  }
  loadError.value = ''
  eggs.value = petsStore.hatchEggs
  jobs.value = petsStore.hatchJobs
  activeCount.value = petsStore.hatchActiveCount
  maxConcurrent.value = petsStore.hatchMaxConcurrent
}

async function onStart(eggId: string): Promise<void> {
  if (busyEgg.value) return
  busyEgg.value = eggId
  try {
    const error = await petsStore.startHatch(eggId)
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    ElMessage.success('已开始孵化')
    emit('log', `开工孵化 ${eggId}`, 'success')
    await refresh()
  } finally {
    busyEgg.value = null
  }
}

async function onClaim(jobId: number): Promise<void> {
  if (busyJob.value !== null) return
  busyJob.value = jobId
  try {
    const error = await petsStore.claimHatch(jobId)
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    ElMessage.success('孵化完成，灵宠已入园')
    emit('log', `领取孵化 #${jobId}`, 'success')
    await refresh()
  } finally {
    busyJob.value = null
  }
}

function statusLabel(status: string): string {
  if (status === 'hatching') return '孵化中'
  if (status === 'ready') return '可领取'
  if (status === 'claimed') return '已领取'
  return status
}

onMounted(() => {
  void refresh()
})
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="header-row">
        <el-text tag="b">灵兽蛋孵化</el-text>
        <el-text type="info" size="small">
          进行中 {{ activeCount }}
          <template v-if="maxConcurrent > 0">/ {{ maxConcurrent }}</template>
        </el-text>
        <el-button size="small" @click="refresh">刷新</el-button>
      </div>
    </template>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
      class="mb"
    />

    <el-text tag="b" size="small">背包中的蛋</el-text>
    <el-empty v-if="eggs.length === 0" description="尚无蛋配置" :image-size="48" />
    <ul v-else class="egg-list">
      <li v-for="egg in eggs" :key="egg.egg_item_id" class="egg-row">
        <div>
          <el-text>{{ egg.name }}</el-text>
          <el-text type="info" size="small" class="meta">
            → {{ egg.species_name || egg.species_id }} · {{ egg.hatch_seconds }}s
            <template v-if="egg.spirit_stones"> · {{ egg.spirit_stones }} 灵石</template>
            · 持有 {{ egg.owned }}
          </el-text>
        </div>
        <el-button
          size="small"
          type="primary"
          :disabled="egg.owned < 1"
          :loading="busyEgg === egg.egg_item_id"
          @click="onStart(egg.egg_item_id)"
        >
          开始孵化
        </el-button>
      </li>
    </ul>

    <el-text tag="b" size="small" class="sub">孵化会话</el-text>
    <el-empty v-if="jobs.length === 0" description="暂无孵化会话" :image-size="40" />
    <ul v-else class="egg-list">
      <li v-for="job in jobs" :key="job.job_id" class="egg-row">
        <div>
          <el-text>#{{ job.job_id }} · {{ job.egg_name }} → {{ job.species_name }}</el-text>
          <el-text type="info" size="small" class="meta">
            {{ statusLabel(job.status) }}
            <template v-if="job.status === 'hatching'">
              · 剩余约 {{ job.remaining_seconds }}s
            </template>
            <template v-if="job.result_pet_id"> · 宠 #{{ job.result_pet_id }}</template>
          </el-text>
        </div>
        <el-button
          v-if="job.status === 'ready'"
          size="small"
          type="success"
          :loading="busyJob === job.job_id"
          @click="onClaim(job.job_id)"
        >
          领取入园
        </el-button>
      </li>
    </ul>

    <el-text type="info" size="small" class="hint">
      DEV：GM「发放工坊材料」会附赠试炼蛋。狐蛋 hatch_seconds=0 可立刻领取。
    </el-text>
  </el-card>
</template>

<style scoped>
.header-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}

.mb {
  margin-bottom: 0.75rem;
}

.egg-list {
  list-style: none;
  margin: 0.35rem 0 0.75rem;
  padding: 0;
}

.egg-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.35rem 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.meta {
  display: block;
}

.sub {
  display: block;
  margin-top: 0.5rem;
}

.hint {
  display: block;
  margin-top: 0.5rem;
}
</style>
