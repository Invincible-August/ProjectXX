<script setup lang="ts">
/**
 * 传修为面板：预览到账（保留率）后确认；炼体/制造业不可传。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useAvatarStore } from '../../stores/avatar'
import { useCharacterStore } from '../../stores/character'
import type { AvatarPublic, AvatarTransferAudit, TransferDirection } from '../../types/avatar'

const props = defineProps<{
  avatar: AvatarPublic
}>()

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const avatarStore = useAvatarStore()
const characterStore = useCharacterStore()
const busy = ref(false)
const direction = ref<TransferDirection>('main_to_avatar')
const amount = ref(10)
const preview = ref<AvatarTransferAudit | null>(null)
const previewError = ref('')

const maxAmount = computed(() => {
  const ch = characterStore.character
  if (!ch) return 0
  if (direction.value === 'main_to_avatar') return ch.cultivation_points
  return props.avatar.cultivation_points
})

const retentionHint = computed(() => {
  const r = props.avatar.transfer_retention_ratio
  if (r == null) return ''
  return `保留率 ${(r * 100).toFixed(0)}%`
})

async function refreshPreview(): Promise<void> {
  previewError.value = ''
  if (amount.value <= 0) {
    preview.value = null
    return
  }
  const { error, data } = await avatarStore.preview(direction.value, amount.value)
  if (error) {
    previewError.value = error
    preview.value = null
    return
  }
  preview.value = data
}

watch([direction, amount], () => {
  void refreshPreview()
}, { immediate: true })

async function onTransfer(): Promise<void> {
  if (busy.value || amount.value <= 0) return
  if (amount.value > maxAmount.value) {
    ElMessage.warning('数量超过可用修为')
    return
  }
  busy.value = true
  try {
    const error = await avatarStore.transfer(direction.value, amount.value)
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    const net = preview.value?.net ?? amount.value
    const dirText = direction.value === 'main_to_avatar' ? '本体→化身' : '化身→本体'
    ElMessage.success(`已传修为：扣 ${amount.value}，到账 ${net}（${dirText}）`)
    emit('log', `传修为扣 ${amount.value} 到账 ${net}：${dirText}`, 'success')
    await refreshPreview()
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never" id="transfer-panel">
    <template #header>
      <el-text tag="b">传修为</el-text>
    </template>

    <el-text type="info" size="small" class="hint">
      {{ avatar.transfer_summary || '仅修为池可互传；炼体度与制造业经验不可传。' }}
      <template v-if="retentionHint"> · {{ retentionHint }}</template>
    </el-text>

    <el-form label-position="top" size="small">
      <el-form-item label="方向">
        <el-radio-group v-model="direction">
          <el-radio value="main_to_avatar">本体 → 化身</el-radio>
          <el-radio value="avatar_to_main">化身 → 本体</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="数量">
        <el-input-number v-model="amount" :min="1" :max="Math.max(1, maxAmount)" />
        <el-text size="small" type="info" class="max-hint">可用 {{ maxAmount }}</el-text>
      </el-form-item>

      <div v-if="preview?.ok" class="preview-box">
        <el-text size="small">
          预览：扣发送方 <b>{{ preview.gross }}</b>，到账 <b>{{ preview.net }}</b>，
          损耗 {{ preview.fee }}（保留率 {{ (preview.retention_ratio * 100).toFixed(0) }}%）
        </el-text>
      </div>
      <el-text v-else-if="previewError" type="danger" size="small">{{ previewError }}</el-text>

      <el-button type="primary" :loading="busy" :disabled="maxAmount <= 0" @click="onTransfer">
        确认转移
      </el-button>
    </el-form>
  </el-card>
</template>

<style scoped>
.hint {
  display: block;
  margin-bottom: 0.75rem;
}

.max-hint {
  margin-left: 0.5rem;
}

.preview-box {
  margin-bottom: 0.75rem;
  padding: 0.5rem 0.65rem;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}
</style>
