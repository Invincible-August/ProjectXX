<script setup lang="ts">
/**
 * 化身挂机方向面板：修灵/炼体/制造业/采矿；禁用项显示解锁境界。
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAvatarStore } from '../../stores/avatar'
import { useCharacterStore } from '../../stores/character'
import type { AvatarFeatureState, AvatarPublic } from '../../types/avatar'
import { idleDirectionLabel } from '../../utils/idleLabels'

const props = defineProps<{
  avatar: AvatarPublic
  features?: AvatarFeatureState[]
}>()

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const avatarStore = useAvatarStore()
const characterStore = useCharacterStore()
const busy = ref(false)

const direction = computed(() => props.avatar.idle_direction)
const inSect = computed(() => Boolean(characterStore.character?.sect?.in_sect))

/** 方向 → 功能 id（采矿复用修灵解锁） */
const DIR_FEATURE: Record<string, string> = {
  spirit: 'idle_spirit',
  body: 'idle_body',
  crafting: 'idle_crafting',
  sect_mining: 'idle_spirit',
}

const DIR_BUTTONS: { key: string; label: string }[] = [
  { key: 'none', label: '停止' },
  { key: 'spirit', label: '修炼' },
  { key: 'body', label: '淬体' },
  { key: 'crafting', label: '制造业修炼' },
  { key: 'sect_mining', label: '采矿' },
]

function featureFor(dir: string): AvatarFeatureState | undefined {
  const fid = DIR_FEATURE[dir]
  if (!fid) return undefined
  return props.features?.find((f) => f.feature_id === fid)
}

function isDirEnabled(dir: string): boolean {
  if (dir === 'none') return true
  if (dir === 'sect_mining' && !inSect.value) return false
  const feat = featureFor(dir)
  if (!feat) return true
  return feat.unlocked
}

function disabledReason(dir: string): string {
  if (dir === 'sect_mining' && !inSect.value) return '需先入宗'
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
    await characterStore.fetchMe()
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
        v-for="btn in DIR_BUTTONS"
        :key="btn.key"
        :disabled="isDirEnabled(btn.key)"
        :content="disabledReason(btn.key)"
        placement="top"
      >
        <el-button
          size="small"
          :type="direction === btn.key ? (btn.key === 'sect_mining' ? 'warning' : 'primary') : 'default'"
          :loading="busy"
          :disabled="!isDirEnabled(btn.key)"
          @click="setDir(btn.key)"
        >
          {{ btn.label }}
        </el-button>
      </el-tooltip>
    </div>

    <el-text type="info" size="small">
      与本体并行；采矿计入宗门矿脉名额，个人灵石入本体钱包并耗体力。
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
