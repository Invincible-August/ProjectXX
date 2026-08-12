<script setup lang="ts">
/**
 * 神识容量 / 负载 / 超载提示条。
 */
import { computed } from 'vue'
import type { DivineSenseReading } from '../../types/avatar'

const props = defineProps<{
  sense: DivineSenseReading | null
}>()

const loadRatio = computed(() => {
  if (!props.sense || props.sense.capacity <= 0) return 0
  return Math.min(1, props.sense.load / props.sense.capacity)
})

const barStatus = computed(() => {
  if (!props.sense) return ''
  if (props.sense.backlash) return 'exception'
  if (props.sense.load > props.sense.soft_cap) return 'warning'
  return 'success'
})

const percent = computed(() => Math.round(loadRatio.value * 100))
</script>

<template>
  <div v-if="sense" class="sense-bar">
    <div class="sense-header">
      <el-text tag="b" size="small">神识</el-text>
      <el-text size="small" type="info">
        负载 {{ sense.load }} / 容量 {{ sense.capacity }}
        （软上限 {{ sense.soft_cap }} · 硬上限 {{ sense.hard_cap }}）
      </el-text>
    </div>
    <el-progress
      :percentage="percent"
      :status="barStatus || undefined"
      :stroke-width="10"
      striped
      striped-flow
    />
    <el-alert
      v-if="sense.backlash"
      :title="sense.backlash_summary || '神识反噬：化身修炼减速'"
      type="warning"
      :closable="false"
      show-icon
      class="sense-alert"
    />
    <el-text v-else-if="sense.load > sense.soft_cap" type="warning" size="small">
      神识超载（{{ sense.zone || 'overload' }}）：战斗属性 ×
      {{ sense.overload_mult?.toFixed(2) ?? '—' }}
    </el-text>
    <el-text v-else type="info" size="small">
      舒适区 · 战斗乘区 1.00
    </el-text>
  </div>
</template>

<style scoped>
.sense-bar {
  margin-bottom: 0.75rem;
}

.sense-header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.5rem;
  margin-bottom: 0.35rem;
}

.sense-alert {
  margin-top: 0.5rem;
}
</style>
