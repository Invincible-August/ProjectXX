<script setup lang="ts">
/**
 * 防守快照条：展示上次更新时间 / 冷却倒计时；手动更新按钮。
 *
 * 文案约定：快照读取「防守预设」，不含挂机瞬时进度；保存布阵不会自动更新快照。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchMySnapshotApi, updateDefenseSnapshotApi } from '../../api/snapshot'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const updatedAt = ref<string | null>(null)
const cooldownSeconds = ref(0)
const loading = ref(false)
const updating = ref(false)
let ticker: ReturnType<typeof setInterval> | null = null

/** 冷却剩余 mm:ss */
const cooldownText = computed(() => {
  const total = cooldownSeconds.value
  if (total <= 0) return ''
  const mm = String(Math.floor(total / 60)).padStart(2, '0')
  const ss = String(total % 60).padStart(2, '0')
  return `${mm}:${ss}`
})

/** 拉取我的快照摘要（触发服务端惰性补刷）。 */
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

/** 手动更新（确认后调用；40045/40046 特判文案）。 */
async function onUpdate(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '将当前「防守预设 + 实时属性」冻结为防守快照，供其他玩家攻打。确认更新？',
      '更新防守快照',
      { confirmButtonText: '更新', cancelButtonText: '取消' },
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
    ElMessage.success('防守快照已更新')
    emit('log', '防守快照已更新（冻结当前防守预设与属性）。', 'success')
  } finally {
    updating.value = false
  }
}

onMounted(() => {
  void loadSnapshot()
  // 本地倒计时递减；到 0 停
  ticker = setInterval(() => {
    if (cooldownSeconds.value > 0) cooldownSeconds.value -= 1
  }, 1000)
})

onUnmounted(() => {
  if (ticker) clearInterval(ticker)
})
</script>

<template>
  <el-card shadow="never">
    <div class="snapshot-bar">
      <div class="snapshot-info">
        <el-text tag="b">防守快照</el-text>
        <el-text type="info" size="small">
          上次更新：{{ updatedAt ? new Date(updatedAt).toLocaleString() : '—' }}
        </el-text>
        <el-text type="info" size="small">
          快照读取防守预设，不含挂机进度；保存布阵不会自动更新快照。
        </el-text>
      </div>
      <el-button
        type="primary"
        size="small"
        :loading="updating || loading"
        :disabled="cooldownSeconds > 0"
        @click="onUpdate"
      >
        <template v-if="cooldownSeconds > 0">冷却 {{ cooldownText }}</template>
        <template v-else>更新防守快照</template>
      </el-button>
    </div>
  </el-card>
</template>

<style scoped>
.snapshot-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.snapshot-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
</style>
