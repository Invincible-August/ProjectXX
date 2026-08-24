<script setup lang="ts">
/**
 * 刷新防守快照：工具条按钮；悬停显示上次更新时间。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchMySnapshotApi, updateDefenseSnapshotApi } from '../../api/snapshot'

const updatedAt = ref<string | null>(null)
const cooldownSeconds = ref(0)
const loading = ref(false)
const updating = ref(false)
let ticker: ReturnType<typeof setInterval> | null = null

const hoverText = computed(() => {
  const when = updatedAt.value
    ? new Date(updatedAt.value).toLocaleString()
    : '—'
  return `上次更新：${when}`
})

async function loadSnapshot(): Promise<void> {
  loading.value = true
  try {
    const envelope = await fetchMySnapshotApi()
    if (envelope.code === 0 && envelope.data) {
      updatedAt.value = envelope.data.updated_at
      cooldownSeconds.value = envelope.data.cooldown_remaining_seconds
    }
  } finally {
    loading.value = false
  }
}

async function onUpdate(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '将当前防守预设与实时属性冻结为快照，供其他玩家攻打。确认刷新？',
      '刷新快照',
      { confirmButtonText: '刷新', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  updating.value = true
  try {
    const envelope = await updateDefenseSnapshotApi()
    if (envelope.code === 40045) {
      ElMessage.warning(envelope.message || '快照更新冷却中')
      return
    }
    if (envelope.code === 40046) {
      ElMessage.warning(envelope.message || '当前状态禁止更新快照')
      return
    }
    if (envelope.code !== 0 || !envelope.data) {
      ElMessage.error(envelope.message || '更新失败')
      return
    }
    cooldownSeconds.value = envelope.data.cooldown_remaining_seconds
    updatedAt.value = new Date().toISOString()
    ElMessage.success('快照已刷新')
  } finally {
    updating.value = false
  }
}

onMounted(() => {
  void loadSnapshot()
  ticker = setInterval(() => {
    if (cooldownSeconds.value > 0) cooldownSeconds.value -= 1
  }, 1000)
})

onUnmounted(() => {
  if (ticker) clearInterval(ticker)
})
</script>

<template>
  <el-tooltip :content="hoverText" placement="bottom">
    <span class="snapshot-btn-wrap">
      <el-button
        size="small"
        :loading="updating || loading"
        :disabled="cooldownSeconds > 0"
        @click="onUpdate"
      >
        刷新快照
      </el-button>
    </span>
  </el-tooltip>
</template>

<style scoped>
.snapshot-btn-wrap {
  display: inline-flex;
}
</style>
