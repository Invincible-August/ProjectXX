<script setup lang="ts">
/**
 * 主动祭坛二次确认（必须先 preview）。
 * 化神期以下禁用（服务端权威；预览带 can_altar）。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useCharacterStore } from '../../stores/character'
import { useFerryStore } from '../../stores/ferry'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
  done: []
}>()

const ferryStore = useFerryStore()
const characterStore = useCharacterStore()
const busy = ref(false)
const acknowledged = ref(false)

const canAltar = computed(() => ferryStore.preview?.can_altar !== false)
const altarBlockReason = computed(
  () =>
    ferryStore.preview?.altar_block_reason ||
    '须达化神期方可主动入轮回（祭坛）',
)
const minMajorLabel = computed(
  () => ferryStore.preview?.min_major_label_zh || '化神',
)
const realmLabel = computed(
  () =>
    characterStore.character?.major_realm_name ||
    characterStore.character?.major_realm ||
    '—',
)

async function loadPreview(): Promise<void> {
  const err = await ferryStore.loadPreview('altar')
  if (err) ElMessage.error(err)
}

onMounted(() => {
  void loadPreview()
})

async function onConfirm(): Promise<void> {
  if (busy.value) return
  if (!ferryStore.preview) {
    ElMessage.warning('请先查看预览')
    await loadPreview()
    return
  }
  if (!canAltar.value) {
    ElMessage.warning(altarBlockReason.value)
    return
  }
  if (!acknowledged.value) {
    ElMessage.warning('请勾选确认清单')
    return
  }
  try {
    await ElMessageBox.confirm(
      [
        '· 境界重置为锻体一层',
        '· 防守快照作废',
        '· 化身解散',
        '· 体质保留',
      ].join('\n'),
      '祭坛轮回二次确认',
      { type: 'warning', confirmButtonText: '确认轮回', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  busy.value = true
  try {
    const err = await ferryStore.altar()
    if (err) throw new Error(err)
    ElMessage.success(ferryStore.lastMessage || '祭坛轮回完成')
    emit('log', ferryStore.lastMessage || '祭坛轮回完成', 'success')
    emit('done')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '祭坛失败'
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
      <el-text tag="b">祭坛确认</el-text>
    </template>

    <el-alert
      v-if="!canAltar"
      :title="altarBlockReason"
      type="warning"
      show-icon
      :closable="false"
      class="gate-alert"
    >
      <el-text size="small">
        当前境界 {{ realmLabel }}；主动入轮回需达到{{ minMajorLabel }}期。
        陨落后待引渡仍可自选入轮回。
      </el-text>
    </el-alert>

    <el-button size="small" @click="loadPreview">刷新预览</el-button>

    <el-checkbox v-model="acknowledged" class="ack" :disabled="!canAltar">
      我已阅读：境界重置 / 快照作废 / 化身解散 / 体质保留
    </el-checkbox>

    <el-button
      type="danger"
      class="confirm-btn"
      :loading="busy"
      :disabled="!acknowledged || !canAltar"
      @click="onConfirm"
    >
      确认主动轮回
    </el-button>
  </el-card>
</template>

<style scoped>
.gate-alert {
  margin-bottom: 0.75rem;
}

.ack {
  display: block;
  margin: 0.75rem 0;
}

.confirm-btn {
  width: 100%;
}
</style>
