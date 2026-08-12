<script setup lang="ts">
/**
 * 化身挂机方向面板：仅列出已解锁方向；禁用项显示解锁境界。
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAvatarStore } from '../../stores/avatar'
import type { AvatarFeatureState, AvatarPublic } from '../../types/avatar'
import { IDLE_DIRECTION_LABELS, idleDirectionLabel } from '../../utils/idleLabels'

const props = defineProps<{
  avatar: AvatarPublic
  features?: AvatarFeatureState[]
}>()

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const avatarStore = useAvatarStore()
const busy = ref(false)

const direction = computed(() => props.avatar.idle_direction)

/** 方向 → 功能 id */
const DIR_FEATURE: Record<string, string> = {
  spirit: 'idle_spirit',
  body: 'idle_body',
  crafting: 'idle_crafting',
}

function featureFor(dir: string): AvatarFeatureState | undefined {
  const fid = DIR_FEATURE[dir]
  if (!fid) return undefined
  return props.features?.find((f) => f.feature_id === fid)
}

function isDirEnabled(dir: string): boolean {
  if (dir === 'none') return true
  const feat = featureFor(dir)
  // 无 features 时回退全开（兼容旧响应）
  if (!feat) return true
  return feat.unlocked
}

function disabledReason(dir: string): string {
  const feat = featureFor(dir)
  if (!feat || feat.unlocked) return ''
  return `需本体达 ${feat.min_major}`
}

async function setDir(dir: string): Promise<void> {
  if (busy.value || direction.value === dir) return
  if (!isDirEnabled(dir)) {
    ElMessage.warning(disabledReason(dir) || '功能未解锁')
    return
  }
  busy.value = true
  try {
    const error = await avatarStore.setIdle(dir)
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    const label = idleDirectionLabel(dir)
    ElMessage.success(`化身方向：${label}`)
    emit('log', `化身切换为 ${label}`, 'success')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">化身挂机</el-text>
    </template>

    <el-text v-if="avatar.status === 'disabled'" type="warning" size="small" class="hint">
      渡劫中不可上阵，挂机仍可用。
    </el-text>

    <div class="pool-row">
      <el-text size="small">修为池 {{ avatar.cultivation_points }}</el-text>
      <el-text size="small" type="info">炼体 {{ avatar.body_tempering_points }}</el-text>
      <el-text size="small" type="info">制造业 {{ avatar.crafting_exp }}</el-text>
    </div>

    <div class="dir-actions">
      <el-tooltip
        v-for="(label, key) in IDLE_DIRECTION_LABELS"
        :key="key"
        :disabled="isDirEnabled(key)"
        :content="disabledReason(key)"
        placement="top"
      >
        <el-button
          size="small"
          :type="direction === key ? 'primary' : 'default'"
          :loading="busy"
          :disabled="!isDirEnabled(key)"
          @click="setDir(key)"
        >
          {{ label }}
        </el-button>
      </el-tooltip>
    </div>

    <el-text type="info" size="small">
      与大厅本体挂机并行；方向由境界功能解锁表控制。
    </el-text>
  </el-card>
</template>

<style scoped>
.hint {
  display: block;
  margin-bottom: 0.5rem;
}

.pool-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.dir-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}
</style>
