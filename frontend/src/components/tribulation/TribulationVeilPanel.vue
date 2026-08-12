<script setup lang="ts">
/**
 * 遮天道具确认与风险文案。
 */
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTribulationStore } from '../../stores/tribulation'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const tribulationStore = useTribulationStore()
const busy = ref(false)

const session = computed(() => tribulationStore.session)
const canVeil = computed(
  () =>
    Boolean(session.value?.veil_selected) &&
    (session.value?.phase === 'committed' || session.value?.phase === 'preparing'),
)

async function onVeil(): Promise<void> {
  if (busy.value || !canVeil.value) return
  try {
    await ElMessageBox.confirm(
      '遮天失败可能升档或重伤，是否仍要检定？',
      '遮天确认',
      { type: 'warning', confirmButtonText: '检定', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  busy.value = true
  try {
    const err = await tribulationStore.runVeil()
    if (err) throw new Error(err)
    ElMessage.info(tribulationStore.lastMessage || '遮天检定完成')
    emit('log', tribulationStore.lastMessage || '遮天检定完成', 'info')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '遮天失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">遮天</el-text>
    </template>
    <el-text size="small" type="info" class="tip">
      成功可降威力档；失败可能升档 / 重伤。可并入开渡，也可单独检定。
    </el-text>
    <el-button
      type="warning"
      size="small"
      :disabled="!canVeil"
      :loading="busy"
      @click="onVeil"
    >
      遮天检定
    </el-button>
    <el-text
      v-if="tribulationStore.lastMessage"
      size="small"
      class="result"
    >
      {{ tribulationStore.lastMessage }}
    </el-text>
  </el-card>
</template>

<style scoped>
.tip {
  display: block;
  margin-bottom: 0.75rem;
}

.result {
  display: block;
  margin-top: 0.5rem;
}
</style>
