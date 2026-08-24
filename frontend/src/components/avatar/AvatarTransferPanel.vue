<script setup lang="ts">
/**
 * 传修为面板：预览到账（保留率）后确认；炼体/制造业不可传。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
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

const retentionPct = computed(() => {
  const live = preview.value?.retention_ratio ?? props.avatar.transfer_retention_ratio ?? 0.8
  return Math.round(live * 100)
})

const dirText = computed(() =>
  direction.value === 'main_to_avatar' ? '本体 → 化身' : '化身 → 本体',
)

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
    ElMessage.success(`已传修为：扣 ${amount.value}，到账 ${net}（${dirText.value}）`)
    emit('log', `传修为扣 ${amount.value} 到账 ${net}：${dirText.value}`, 'success')
    await refreshPreview()
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never" id="transfer-panel">
    <template #header>
      <div class="transfer-header">
        <el-text tag="b">传修为</el-text>
        <el-tooltip placement="bottom-start" effect="dark" :show-after="200" popper-class="game-hover-tip">
          <template #content>
            <div class="transfer-help">
              <p>{{ avatar.transfer_summary || '互传修为到账按保留率结算，损耗不可逆。' }}</p>
              <p>当前保留率 {{ retentionPct }}%（默认 80%，会随功法变化）。</p>
              <p>仅修为池可互传；炼体度与制造业经验不可传。</p>
              <p>到账 = floor(发送量 × 保留率)。</p>
            </div>
          </template>
          <button type="button" class="transfer-info" aria-label="查看传修为说明">
            <el-icon :size="14"><InfoFilled /></el-icon>
          </button>
        </el-tooltip>
      </div>
    </template>

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
        <div class="preview-row">
          <el-text size="small" type="info">方向</el-text>
          <el-text size="small">{{ dirText }}</el-text>
        </div>
        <div class="preview-row">
          <el-text size="small" type="info">发送</el-text>
          <el-text size="small">−{{ preview.gross }}</el-text>
        </div>
        <div class="preview-row">
          <el-text size="small" type="info">到账</el-text>
          <el-text size="small" type="success">+{{ preview.net }}</el-text>
        </div>
        <div class="preview-row">
          <el-text size="small" type="info">损耗</el-text>
          <el-text size="small">{{ preview.fee }}（保留 {{ retentionPct }}%）</el-text>
        </div>
      </div>
      <el-text v-else-if="previewError" type="danger" size="small">{{ previewError }}</el-text>

      <el-button type="primary" :loading="busy" :disabled="maxAmount <= 0" @click="onTransfer">
        确认转移
      </el-button>
    </el-form>
  </el-card>
</template>

<style scoped>
.transfer-header {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.transfer-info {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--el-text-color-secondary);
  cursor: help;
}

.max-hint {
  margin-left: 0.5rem;
}

.preview-box {
  margin-bottom: 0.75rem;
  padding: 0.55rem 0.7rem;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 0.28rem;
}

.preview-row {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
}
</style>

<style>
.transfer-help {
  max-width: 280px;
  line-height: 1.5;
}
.transfer-help p {
  margin: 0 0 0.35rem;
}
.transfer-help p:last-child {
  margin-bottom: 0;
}
</style>
