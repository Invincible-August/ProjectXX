<script setup lang="ts">
/**
 * 离线收益预览与一键领取（M2）。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { previewOfflineApi } from '../api/idle'
import { useCharacterStore } from '../stores/character'
import type { OfflinePending } from '../types/character'
import { idleDirectionLabel } from '../utils/idleLabels'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const characterStore = useCharacterStore()
const busy = ref(false)
const loadingPreview = ref(false)
const pending = ref<OfflinePending | null>(null)

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

/**
 * 打开时刷新 preview（幂等）。
 */
async function refreshPreview(): Promise<void> {
  loadingPreview.value = true
  try {
    const envelope = await previewOfflineApi()
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || '预览离线收益失败')
    }
    pending.value = envelope.data.pending
    if (envelope.data.character) {
      characterStore.applyCharacter(envelope.data.character)
    }
    if (!envelope.data.has_pending) {
      pending.value = characterStore.character?.offline_pending ?? null
    }
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '预览失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    loadingPreview.value = false
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      pending.value = characterStore.character?.offline_pending ?? null
      void refreshPreview()
    }
  },
)

async function onClaim(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const data = await characterStore.claimOffline()
    ElMessage.success('已领取离线收益')
    emit(
      'log',
      `离线领取 ${data.settled_ticks} 周天：修为 +${data.gained_cultivation}，炼体 +${data.gained_body ?? 0}，制造业 +${data.gained_crafting ?? 0}，灵石 -${data.spent_spirit_stones}`,
      'success',
    )
    visible.value = false
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '领取失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="离线收益"
    width="420px"
    append-to-body
    destroy-on-close
  >
    <el-skeleton v-if="loadingPreview && !pending" animated :rows="4" />
    <template v-else-if="pending">
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="有效周天">
          {{ pending.settled_ticks }}
        </el-descriptions-item>
        <el-descriptions-item label="离线帽">
          {{ pending.cap_hours }} 小时
          <el-tag v-if="pending.capped" size="small" type="warning" class="ml">
            已触帽
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="墙钟时长">
          {{ Math.round(pending.wall_elapsed_seconds / 3600) }} 小时（约）
        </el-descriptions-item>
        <el-descriptions-item label="方向">
          {{ idleDirectionLabel(pending.direction) }}
        </el-descriptions-item>
        <el-descriptions-item label="修为">+{{ pending.gained_cultivation }}</el-descriptions-item>
        <el-descriptions-item label="淬体度">+{{ pending.gained_body }}</el-descriptions-item>
        <el-descriptions-item label="制造业经验">
          +{{ pending.gained_crafting }}
        </el-descriptions-item>
        <el-descriptions-item label="灵石消耗">
          -{{ pending.spent_spirit_stones }}
        </el-descriptions-item>
      </el-descriptions>
      <el-alert
        v-if="pending.is_stalled"
        class="mt"
        title="结算期间曾因灵石不足停滞"
        type="warning"
        :closable="false"
        show-icon
      />
    </template>
    <el-empty v-else description="暂无待领取离线收益" :image-size="64" />

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button
        type="primary"
        :disabled="!pending"
        :loading="busy"
        @click="onClaim"
      >
        领取收益
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.ml {
  margin-left: 0.35rem;
}
.mt {
  margin-top: 0.75rem;
}
</style>
