<script setup lang="ts">
/**
 * 修炼面板：本体三向挂机；已凝练化身后嵌化身线程；资源分配 / 进阶弹窗入口。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import AllocatePanel from './AllocatePanel.vue'
import BreakthroughPanel from './BreakthroughPanel.vue'
import IdleEnvPanel from './IdleEnvPanel.vue'
import AvatarIdlePanel from './avatar/AvatarIdlePanel.vue'
import { useActivityGate } from '../composables/useActivityGate'
import { useAvatarStore } from '../stores/avatar'
import { useCharacterStore } from '../stores/character'
import { useWorldStore } from '../stores/world'
import type { IdleDirection, IdleSyncData } from '../types/idle'
import { startMine } from '../api/sect'
import { formatTickGainLabel } from '../utils/idleRateClient'
import { idleDirectionLabel } from '../utils/idleLabels'
import { isProductiveDirection } from '../utils/idlePredict'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
  needClaimOffline: []
  settleTick: [data: IdleSyncData]
  settleStop: [data: IdleSyncData]
  avatarSettleTick: [gains: IdleSyncData['avatar_gains']]
  avatarSettleStop: [gains: IdleSyncData['avatar_gains']]
}>()

const characterStore = useCharacterStore()
const avatarStore = useAvatarStore()
const worldStore = useWorldStore()
const { canEnterIdle, blockReason, activity } = useActivityGate()
const busy = ref(false)
const creditFlash = ref(false)
const allocateOpen = ref(false)
const advanceOpen = ref(false)
let creditFlashTimer: ReturnType<typeof setTimeout> | null = null

const character = computed(() => characterStore.character)
const display = computed(() => characterStore.display)
const direction = computed(() => character.value?.idle_direction ?? 'none')
/** 修灵/炼体/制造业产出中 */
const isActive = computed(() => isProductiveDirection(direction.value))
/** 含采矿：占用修炼态 */
const isMining = computed(() => direction.value === 'sect_mining')
const showStalled = computed(
  () => display.value?.is_stalled === true || character.value?.is_stalled === true,
)
const hasPending = computed(() => Boolean(character.value?.offline_pending))
const hasAvatar = computed(() => Boolean(character.value?.has_avatar))
const inSect = computed(() => Boolean(character.value?.sect?.in_sect))

/**
 * 凝练后拉化身面板与功能解锁，供修炼区按钮禁用态。
 */
async function ensureAvatarLoaded(): Promise<void> {
  if (!hasAvatar.value) return
  if (!avatarStore.avatar) {
    await avatarStore.load()
  }
  if (!avatarStore.features?.features?.length) {
    await avatarStore.loadFeatures()
  }
}

/** 开始某方向修炼是否应禁用（停止当前方向始终可点，除非 pending） */
function startDisabled(target: IdleDirection): boolean {
  if (hasPending.value) return true
  if (direction.value === target) return false
  if (isMining.value) return false
  return !canEnterIdle.value
}

const enterIdleBlockHint = computed(
  () =>
    blockReason('enter_idle') ||
    (activity.value.craft_running > 0 ? '工坊进行中，请先完成后再修炼' : null),
)

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
  const ch = character.value
  if (!ch) return ''
  // 依赖 world 时辰/天气/idle_preview，环境一变立刻重算
  return formatTickGainLabel(
    ch,
    worldStore.idlePreview,
    worldStore.shichen,
    worldStore.weather,
    ch.idle_direction,
  )
})

function triggerCreditFlash(): void {
  creditFlash.value = true
  if (creditFlashTimer !== null) clearTimeout(creditFlashTimer)
  creditFlashTimer = setTimeout(() => {
    creditFlash.value = false
    creditFlashTimer = null
  }, 1200)
}

watch(
  () => display.value?.predicted_ticks ?? 0,
  (next, prev) => {
    if (next > prev && isActive.value) triggerCreditFlash()
  },
)

watch(hasAvatar, (ready) => {
  if (ready) void ensureAvatarLoaded()
})

onMounted(() => {
  void ensureAvatarLoaded()
})

onBeforeUnmount(() => {
  if (creditFlashTimer !== null) {
    clearTimeout(creditFlashTimer)
    creditFlashTimer = null
  }
})

/**
 * 切换到指定方向，或再次点击停止。
 *
 * @param target - 目标方向
 */
async function setDirection(target: IdleDirection): Promise<void> {
  if (busy.value || !character.value) return
  if (hasPending.value) {
    ElMessage.warning('请先领取离线收益')
    emit('needClaimOffline')
    return
  }
  busy.value = true
  try {
    if (direction.value === target) {
      const data = await characterStore.setDirection('none')
      emit('settleStop', data)
      return
    }
    if (!isMining.value && !canEnterIdle.value && target !== 'none') {
      const reason = enterIdleBlockHint.value || '当前不可修炼'
      ElMessage.warning(reason)
      emit('log', reason, 'warning')
      return
    }
    const data = await characterStore.setDirection(target)
    const names: Record<string, string> = {
      spirit: '修炼',
      body: '淬体',
      crafting: '制造业修炼',
      none: '空闲',
    }
    ElMessage.success(`已开始${names[target] ?? target}`)
    emit('log', `开始${names[target] ?? target}。`, 'success')
    if (data.settled_ticks > 0 || data.avatar_gains?.settled_ticks) {
      emit('settleTick', data)
    }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '切换修炼失败'
    ElMessage.error(msg)
    emit('log', msg, 'warning')
  } finally {
    busy.value = false
  }
}

/** 结束采矿。 */
async function stopMining(): Promise<void> {
  if (busy.value || !character.value) return
  busy.value = true
  try {
    const data = await characterStore.setDirection('none')
    emit('log', '已结束采矿。', 'info')
    if (data.settled_ticks > 0) {
      emit('settleTick', data)
    }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '结束采矿失败'
    ElMessage.error(msg)
    emit('log', msg, 'warning')
  } finally {
    busy.value = false
  }
}

/** 开始采矿（宗门矿脉名额）。 */
async function startMining(): Promise<void> {
  if (busy.value || !character.value) return
  if (hasPending.value) {
    ElMessage.warning('请先领取离线收益')
    emit('needClaimOffline')
    return
  }
  if (!inSect.value) {
    ElMessage.warning('需先入宗')
    return
  }
  if (!canEnterIdle.value) {
    const reason = enterIdleBlockHint.value || '当前不可采矿'
    ElMessage.warning(reason)
    emit('log', reason, 'warning')
    return
  }
  busy.value = true
  try {
    const envelope = await startMine()
    if (envelope.code !== 0) {
      ElMessage.error(envelope.message || '开始采矿失败')
      emit('log', envelope.message || '开始采矿失败', 'warning')
      return
    }
    await characterStore.fetchMe()
    ElMessage.success('已开始采矿')
    emit('log', '开始采矿。', 'success')
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '开始采矿失败'
    ElMessage.error(msg)
    emit('log', msg, 'warning')
  } finally {
    busy.value = false
  }
}

function onMiningClick(): void {
  if (isMining.value) {
    void stopMining()
    return
  }
  void startMining()
}
</script>

<template>
  <el-card shadow="never" class="idle-panel">
    <template #header>
      <div class="idle-header">
        <el-text tag="b">修炼区</el-text>
        <div class="idle-header-actions">
          <el-button type="warning" size="small" @click="allocateOpen = true">
            资源分配
          </el-button>
          <el-button type="danger" size="small" @click="advanceOpen = true">
            进阶
          </el-button>
        </div>
      </div>
    </template>

    <template v-if="character">
      <div class="thread-block">
        <div class="thread-title">
          <el-text tag="b" size="small">本体</el-text>
          <el-tag size="small" type="info">{{ idleDirectionLabel(character.idle_direction) }}</el-tag>
        </div>

        <!-- 修炼/淬体/制造业修炼：仅环境修正行；采矿保留速度与推算 -->
        <el-descriptions
          v-if="isMining"
          :column="1"
          size="small"
          class="idle-desc"
        >
          <el-descriptions-item label="预估速度">
            每 {{ character.idle_tick_seconds }}s：{{ poolGainLabel }} / 耗体力
          </el-descriptions-item>
          <el-descriptions-item v-if="display" label="实时推算">
            灵石 {{ display.spirit_stones }} · 自开始起满一段后结算灵石并扣体力
          </el-descriptions-item>
        </el-descriptions>

        <IdleEnvPanel
          :idle-env="character.idle_env"
          :world-idle-preview="worldStore.idlePreview"
          :direction="direction"
        />

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
            :status="creditFlash ? 'success' : undefined"
          />
          <div class="idle-tick-meta">
            <el-text size="small" type="info">
              本周天预计（实时环境）：{{ poolGainLabel }}
            </el-text>
            <el-text v-if="creditFlash" size="small" type="success" class="idle-tick-flash">
              本周天收益已并入池
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

        <el-alert
          v-if="!isActive && enterIdleBlockHint"
          :title="enterIdleBlockHint"
          type="info"
          show-icon
          :closable="false"
          class="idle-stall"
        />

        <div class="idle-actions">
          <el-button
            size="small"
            :type="direction === 'spirit' ? 'primary' : 'default'"
            :loading="busy"
            :disabled="startDisabled('spirit')"
            @click="setDirection('spirit')"
          >
            修炼
          </el-button>
          <el-button
            size="small"
            :type="direction === 'body' ? 'primary' : 'default'"
            :loading="busy"
            :disabled="startDisabled('body')"
            @click="setDirection('body')"
          >
            淬体
          </el-button>
          <el-button
            size="small"
            :type="direction === 'crafting' ? 'primary' : 'default'"
            :loading="busy"
            :disabled="startDisabled('crafting')"
            @click="setDirection('crafting')"
          >
            制造业
          </el-button>
          <el-tooltip :disabled="inSect || isMining" content="需先入宗" placement="top">
            <el-button
              size="small"
              :type="isMining ? 'warning' : 'default'"
              :loading="busy"
              :disabled="hasPending || (!inSect && !isMining)"
              @click="onMiningClick"
            >
              采矿
            </el-button>
          </el-tooltip>
        </div>
      </div>

      <AvatarIdlePanel
        v-if="hasAvatar"
        :avatar="avatarStore.avatar"
        :features="avatarStore.features?.features"
        @log="(msg, level) => emit('log', msg, level)"
        @settle-stop="(gains) => emit('avatarSettleStop', gains)"
        @settle-tick="(gains) => emit('avatarSettleTick', gains)"
      />

      <el-alert
        v-if="hasPending"
        title="有未领取离线收益：请先领取后再切换或停止修炼"
        type="info"
        show-icon
        :closable="false"
        class="idle-stall"
      />
    </template>

    <el-empty v-else description="暂无角色" :image-size="48" />

    <el-dialog
      v-model="allocateOpen"
      title="资源分配"
      width="520px"
      destroy-on-close
      append-to-body
      class="idle-feature-dialog"
    >
      <AllocatePanel @log="(msg, level) => emit('log', msg, level)" />
    </el-dialog>

    <el-dialog
      v-model="advanceOpen"
      title="进阶"
      width="560px"
      destroy-on-close
      append-to-body
      class="idle-feature-dialog"
    >
      <BreakthroughPanel @log="(msg, level) => emit('log', msg, level)" />
    </el-dialog>
  </el-card>
</template>

<style scoped>
.idle-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.idle-header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.thread-block {
  margin-bottom: 0.85rem;
}

.thread-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.35rem;
}

.idle-desc {
  margin-bottom: 0.5rem;
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

.idle-tick-flash {
  font-weight: 600;
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
