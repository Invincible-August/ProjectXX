<script setup lang="ts">
/**
 * 化身修炼线程：嵌在大厅修炼区本体块下方；切方向走 /avatar/idle。
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAvatarStore } from '../../stores/avatar'
import { useCharacterStore } from '../../stores/character'
import type { AvatarFeatureState, AvatarPublic } from '../../types/avatar'
import type { IdleDirection } from '../../types/idle'
import { idleDirectionLabel } from '../../utils/idleLabels'
import { isProductiveDirection } from '../../utils/idlePredict'

const props = defineProps<{
  avatar?: AvatarPublic | null
  features?: AvatarFeatureState[]
}>()

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
  settleStop: [gains: import('../../types/idle').IdleSyncData['avatar_gains']]
  settleTick: [gains: import('../../types/idle').IdleSyncData['avatar_gains']]
}>()

const avatarStore = useAvatarStore()
const characterStore = useCharacterStore()
const busy = ref(false)

const avatar = computed(
  () => props.avatar ?? avatarStore.avatar,
)
const features = computed(
  () =>
    props.features ??
    avatar.value?.features ??
    avatarStore.features?.features ??
    [],
)

const direction = computed(
  () =>
    avatar.value?.idle_direction ??
    characterStore.character?.avatar_summary?.idle_direction ??
    characterStore.character?.dual_idle_preview?.avatar_idle_direction ??
    'none',
)
const directionName = computed(() => idleDirectionLabel(String(direction.value)))
const inSect = computed(() => Boolean(characterStore.character?.sect?.in_sect))
const hasPending = computed(() => Boolean(characterStore.character?.offline_pending))
const display = computed(() => characterStore.avatarDisplay)
const isActive = computed(() => isProductiveDirection(String(direction.value)))
const isMining = computed(() => direction.value === 'sect_mining')
const showStalled = computed(() => display.value?.is_stalled === true)

const tickPercent = computed(() => {
  const ratio = display.value?.tick_progress_ratio ?? 0
  if (!Number.isFinite(ratio)) return 0
  return Math.max(0, Math.min(100, Math.round(ratio * 100)))
})

const secondsLeftInTick = computed(() => {
  const d = display.value
  if (!d || (!isActive.value && !isMining.value) || showStalled.value) return null
  const left = Math.ceil(d.tick_seconds - d.seconds_into_tick)
  return Math.max(0, left)
})

const miningTickPercent = computed(() => {
  if (!isMining.value || !display.value) return 0
  const ratio = display.value.tick_progress_ratio ?? 0
  if (!Number.isFinite(ratio)) return 0
  return Math.max(0, Math.min(100, Math.round(ratio * 100)))
})

const miningGainHint = computed(() => poolGainLabel.value || '个人灵石（环境修正中）')

const poolGainLabel = computed(() => {
  const preview = characterStore.character?.dual_idle_preview
  const dir = String(direction.value)
  if (!preview) return ''
  let label = ''
  if (dir === 'spirit') label = `修为 +${preview.avatar_cultivation_per_tick ?? 0}`
  else if (dir === 'body') label = `淬体度 +${preview.avatar_body_per_tick ?? 0}`
  else if (dir === 'crafting') label = `制造业经验 +${preview.avatar_crafting_per_tick ?? 0}`
  else if (dir === 'sect_mining') return '个人灵石（计入宗门矿脉）'
  else return ''
  const stones = Number(preview.avatar_stones_per_tick || 0)
  if (stones > 0 && (dir === 'spirit' || dir === 'body' || dir === 'crafting')) {
    return `${label}，灵石 -${stones}`
  }
  return label
})

/** 方向 → 功能 id（采矿复用修灵解锁） */
const DIR_FEATURE: Record<string, string> = {
  spirit: 'idle_spirit',
  body: 'idle_body',
  crafting: 'idle_crafting',
  sect_mining: 'idle_spirit',
}

function featureFor(dir: string): AvatarFeatureState | undefined {
  const fid = DIR_FEATURE[dir]
  if (!fid) return undefined
  return features.value.find((f) => f.feature_id === fid)
}

function isDirEnabled(dir: string): boolean {
  if (dir === 'none') return true
  if (dir === 'sect_mining' && !inSect.value) return false
  const feat = featureFor(dir)
  if (!feat) return true
  return feat.unlocked
}

function disabledReason(dir: string): string {
  if (hasPending.value) return '请先领取离线收益'
  if (dir === 'sect_mining' && !inSect.value) return '需先入宗'
  const feat = featureFor(dir)
  if (!feat || feat.unlocked) return ''
  return `需本体达 ${feat.min_major}`
}

function startDisabled(target: IdleDirection | string): boolean {
  if (hasPending.value) return true
  if (direction.value === target) return false
  return !isDirEnabled(String(target))
}

/**
 * 切换化身方向；再点当前方向则停止。
 *
 * @param target - 目标方向
 */
async function setDirection(target: IdleDirection | string): Promise<void> {
  if (busy.value) return
  if (hasPending.value) {
    ElMessage.warning('请先领取离线收益')
    emit('log', '请先领取离线收益', 'warning')
    return
  }
  const next = direction.value === target ? 'none' : String(target)
  if (next !== 'none' && !isDirEnabled(next)) {
    ElMessage.warning(disabledReason(next) || '功能未解锁')
    return
  }
  busy.value = true
  try {
    const { error, idleGains } = await avatarStore.setIdle(next)
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    if (next === 'none') {
      emit('settleStop', idleGains)
      return
    }
    const label = idleDirectionLabel(next)
    ElMessage.success(`已开始${label}`)
    emit('log', `化身开始${label}。`, 'success')
    if (idleGains && Number(idleGains.settled_ticks || 0) > 0) {
      emit('settleTick', idleGains)
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="thread-block">
    <div class="thread-title">
      <el-text tag="b" size="small">化身</el-text>
      <el-tag size="small" type="info">{{ directionName }}</el-tag>
    </div>

    <div v-if="isActive && display" class="idle-tick">
      <div class="idle-tick-label">
        <el-text size="small">本回合修炼</el-text>
        <el-text size="small" type="info">
          <template v-if="showStalled || hasPending">已暂停</template>
          <template v-else-if="secondsLeftInTick != null">
            还剩 {{ secondsLeftInTick }}s
          </template>
        </el-text>
      </div>
      <el-progress
        :percentage="showStalled || hasPending ? 0 : tickPercent"
        :stroke-width="12"
        :striped="isActive && !showStalled && !hasPending"
        :striped-flow="isActive && !showStalled && !hasPending"
      />
      <div class="idle-tick-meta">
        <el-text size="small" type="info">
          本周天预计（实时环境）：{{ poolGainLabel }}
        </el-text>
      </div>
    </div>

    <div v-else-if="isMining && display" class="idle-tick">
      <div class="idle-tick-label">
        <el-text size="small">本回合采矿</el-text>
        <el-text size="small" type="info">
          <template v-if="hasPending">已暂停</template>
          <template v-else-if="secondsLeftInTick != null">
            还剩 {{ secondsLeftInTick }}s
          </template>
        </el-text>
      </div>
      <el-progress
        :percentage="hasPending ? 0 : miningTickPercent"
        :stroke-width="12"
        :striped="!hasPending"
        :striped-flow="!hasPending"
        status="warning"
      />
      <div class="idle-tick-meta">
        <el-text size="small" type="info">{{ miningGainHint }}</el-text>
      </div>
    </div>

    <el-alert
      v-if="showStalled"
      title="灵石不足，修炼停滞；可通过战斗获取灵石"
      type="warning"
      show-icon
      :closable="false"
      class="idle-stall"
    />

    <div class="idle-actions">
      <el-tooltip
        :disabled="isDirEnabled('spirit') && !hasPending"
        :content="disabledReason('spirit')"
        placement="top"
      >
        <el-button
          size="small"
          :type="direction === 'spirit' ? 'primary' : 'default'"
          :loading="busy"
          :disabled="startDisabled('spirit')"
          @click="setDirection('spirit')"
        >
          修炼
        </el-button>
      </el-tooltip>
      <el-tooltip
        :disabled="isDirEnabled('body') && !hasPending"
        :content="disabledReason('body')"
        placement="top"
      >
        <el-button
          size="small"
          :type="direction === 'body' ? 'primary' : 'default'"
          :loading="busy"
          :disabled="startDisabled('body')"
          @click="setDirection('body')"
        >
          淬体
        </el-button>
      </el-tooltip>
      <el-tooltip
        :disabled="isDirEnabled('crafting') && !hasPending"
        :content="disabledReason('crafting')"
        placement="top"
      >
        <el-button
          size="small"
          :type="direction === 'crafting' ? 'primary' : 'default'"
          :loading="busy"
          :disabled="startDisabled('crafting')"
          @click="setDirection('crafting')"
        >
          制造业
        </el-button>
      </el-tooltip>
      <el-tooltip
        :disabled="isDirEnabled('sect_mining') && !hasPending"
        :content="disabledReason('sect_mining')"
        placement="top"
      >
        <el-button
          size="small"
          :type="isMining ? 'warning' : 'default'"
          :loading="busy"
          :disabled="startDisabled('sect_mining')"
          @click="setDirection('sect_mining')"
        >
          采矿
        </el-button>
      </el-tooltip>
    </div>
  </div>
</template>

<style scoped>
.thread-block {
  margin-bottom: 0.85rem;
  padding-top: 0.75rem;
  border-top: 1px dashed var(--el-border-color);
}

.thread-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.35rem;
}

.idle-tick {
  margin-bottom: 0.75rem;
  padding: 0.5rem 0.6rem;
  border-radius: 6px;
  background: linear-gradient(180deg, rgba(64, 158, 255, 0.08), transparent);
}

.idle-tick-label {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.25rem;
}

.idle-tick-meta {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  margin-top: 0.35rem;
}

.idle-stall {
  margin-bottom: 0.75rem;
}

.idle-actions {
  display: flex;
  flex-wrap: nowrap;
  gap: 0.25rem;
}

.idle-actions :deep(.el-button) {
  flex: 1 1 0;
  min-width: 0;
  padding: 5px 4px;
  font-size: 12px;
}
</style>
