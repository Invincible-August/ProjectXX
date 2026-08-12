<script setup lang="ts">
/**
 * 渡劫批次结算 / 一键跳过（禁止逐雷）。
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useTribulationStore } from '../../stores/tribulation'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
  finished: []
}>()

const tribulationStore = useTribulationStore()
const busy = ref(false)

const session = computed(() => tribulationStore.session)
const progressPct = computed(() => {
  const s = session.value
  if (!s || !s.strike_total) return 0
  return Math.min(100, Math.round((s.strike_done / s.strike_total) * 100))
})

async function onBatch(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await tribulationStore.wave()
    if (err) throw new Error(err)
    for (const ev of tribulationStore.lastEvents) {
      emit('log', ev.text || ev.type, 'info')
      if (ev.type === 'guardian') {
        ElMessage.warning('灵宝护主！威力降档 / 怜悯档伤害降至 1%')
      }
    }
    if (tribulationStore.isFinished) emit('finished')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '批次结算失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function onSkip(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await tribulationStore.skipToEnd()
    if (err) throw new Error(err)
    emit('log', tribulationStore.lastMessage || '一键结算完成', 'info')
    emit('finished')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '一键结算失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never" class="resolve-panel">
    <template #header>
      <el-text tag="b">雷劫结算</el-text>
    </template>

    <el-text size="small" type="info" class="tip">
      千劫 / 万劫仅支持批次与一键跳过，禁止逐雷微操。
    </el-text>

    <el-progress
      :percentage="progressPct"
      :stroke-width="12"
      striped
      striped-flow
      class="prog"
    />
    <el-text size="small">
      {{ session?.strike_done ?? 0 }} / {{ session?.strike_total ?? 0 }}
      · 准备格剩余
      {{ (session?.prep_slots ?? []).filter((s) => s.item_uid).length }}
    </el-text>

    <div v-if="session?.guardian_used" class="guardian">
      <el-tag type="danger" effect="dark">灵宝护主已触发</el-tag>
    </div>

    <ul v-if="session?.batch_log?.length" class="batch-log">
      <li v-for="(line, i) in session.batch_log.slice(-12)" :key="i">
        <el-text size="small">{{ line }}</el-text>
      </li>
    </ul>

    <div class="actions">
      <el-button type="primary" :loading="busy" @click="onBatch">下一批</el-button>
      <el-button type="danger" plain :loading="busy" @click="onSkip">
        一键跳过到结束
      </el-button>
    </div>
  </el-card>
</template>

<style scoped>
.tip {
  display: block;
  margin-bottom: 0.75rem;
}

.prog {
  margin-bottom: 0.5rem;
}

.guardian {
  margin: 0.5rem 0;
}

.batch-log {
  list-style: none;
  padding: 0;
  margin: 0.5rem 0;
  max-height: 160px;
  overflow-y: auto;
}

.batch-log li {
  margin-bottom: 0.2rem;
}

.actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.75rem;
  flex-wrap: wrap;
}
</style>
