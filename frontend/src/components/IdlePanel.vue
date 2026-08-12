<script setup lang="ts">
/**
 * 修炼面板：本体三向 + 化身线程进度（M2 / M4）。
 *
 * 本体可切换方向；化身进度只读展示，切方向去 /avatar。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import IdleEnvPanel from './IdleEnvPanel.vue'
import { useActivityGate } from '../composables/useActivityGate'
import { useCharacterStore } from '../stores/character'
import { useWorldStore } from '../stores/world'
import type { IdleDirection } from '../types/idle'
import { formatTickGainLabel } from '../utils/idleRateClient'
import { isProductiveDirection } from '../utils/idlePredict'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
  needClaimOffline: []
}>()

const router = useRouter()
const characterStore = useCharacterStore()
const worldStore = useWorldStore()
const { canEnterIdle, blockReason, modeLabel, activity } = useActivityGate()
const busy = ref(false)
const creditFlash = ref(false)
const avatarCreditFlash = ref(false)
let creditFlashTimer: ReturnType<typeof setTimeout> | null = null
let avatarFlashTimer: ReturnType<typeof setTimeout> | null = null

const character = computed(() => characterStore.character)
const display = computed(() => characterStore.display)
const avatarDisplay = computed(() => characterStore.avatarDisplay)
const direction = computed(() => character.value?.idle_direction ?? 'none')
const isActive = computed(() => isProductiveDirection(direction.value))
const showStalled = computed(
  () => display.value?.is_stalled === true || character.value?.is_stalled === true,
)
const hasPending = computed(() => Boolean(character.value?.offline_pending))

/** 开始某方向修炼是否应禁用（停止当前方向始终可点，除非 pending） */
function startDisabled(target: IdleDirection): boolean {
  if (hasPending.value) return true
  // 已在该方向：按钮是「停止」，不拦
  if (direction.value === target) return false
  // 从其它方向切换或从 none 进入：须 can_enter_idle
  return !canEnterIdle.value
}

const enterIdleBlockHint = computed(
  () =>
    blockReason('enter_idle') ||
    (activity.value.craft_running > 0 ? '工坊进行中，请先完成后再修炼' : null),
)

const hasAvatar = computed(() => Boolean(character.value?.has_avatar))
const avatarDirection = computed(
  () =>
    character.value?.dual_idle_preview?.avatar_idle_direction ??
    character.value?.avatar_summary?.idle_direction ??
    'none',
)
const avatarActive = computed(() => isProductiveDirection(avatarDirection.value))
const avatarShowStalled = computed(
  () => avatarDisplay.value?.is_stalled === true,
)

const directionNames: Record<string, string> = {
  none: '待机',
  spirit: '修灵',
  body: '炼体',
  crafting: '制造业',
}

const tickPercent = computed(() => {
  const ratio = display.value?.tick_progress_ratio ?? 0
  if (!Number.isFinite(ratio)) return 0
  return Math.max(0, Math.min(100, Math.round(ratio * 100)))
})

const avatarTickPercent = computed(() => {
  const ratio = avatarDisplay.value?.tick_progress_ratio ?? 0
  if (!Number.isFinite(ratio)) return 0
  return Math.max(0, Math.min(100, Math.round(ratio * 100)))
})

const secondsLeftInTick = computed(() => {
  const d = display.value
  if (!d || !isActive.value || showStalled.value) return null
  const left = Math.ceil(d.tick_seconds - d.seconds_into_tick)
  return Math.max(0, left)
})

const avatarSecondsLeft = computed(() => {
  const d = avatarDisplay.value
  if (!d || !avatarActive.value || avatarShowStalled.value || hasPending.value) {
    return null
  }
  const left = Math.ceil(d.tick_seconds - d.seconds_into_tick)
  return Math.max(0, left)
})

/**
 * 当前方向有效挂机速率（浏览器实时计算：基础速率 × 当前时辰/天气/标签）。
 * 数据来自角色面板 + 世界轮询已有的 idle_preview，不额外请求服务器。
 *
 * @returns 展示文案，如「修为 +12」
 */
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

/**
 * 化身本片预计：用 dual_idle_preview 基础速率 × 当前世界环境乘区（展示用）。
 */
const avatarPoolGainLabel = computed(() => {
  const ch = character.value
  const preview = ch?.dual_idle_preview
  const dir = avatarDirection.value
  if (!ch || !preview) return ''
  // 构造临时角色字段复用同一套客户端公式
  const synthetic: typeof ch = {
    ...ch,
    idle_direction: dir,
    idle_cultivation_per_tick: preview.avatar_cultivation_per_tick ?? 0,
    idle_body_per_tick: preview.avatar_body_per_tick ?? 0,
    idle_crafting_per_tick: preview.avatar_crafting_per_tick ?? 0,
    // 化身暂不套本体灵根标签，避免高估
    idle_env: undefined,
  }
  return formatTickGainLabel(
    synthetic,
    worldStore.idlePreview,
    worldStore.shichen,
    worldStore.weather,
    dir,
  )
})

const avatarStonesPerTick = computed(
  () => character.value?.dual_idle_preview?.avatar_stones_per_tick ?? 0,
)

function triggerCreditFlash(): void {
  creditFlash.value = true
  if (creditFlashTimer !== null) clearTimeout(creditFlashTimer)
  creditFlashTimer = setTimeout(() => {
    creditFlash.value = false
    creditFlashTimer = null
  }, 1200)
}

function triggerAvatarCreditFlash(): void {
  avatarCreditFlash.value = true
  if (avatarFlashTimer !== null) clearTimeout(avatarFlashTimer)
  avatarFlashTimer = setTimeout(() => {
    avatarCreditFlash.value = false
    avatarFlashTimer = null
  }, 1200)
}

watch(
  () => display.value?.predicted_ticks ?? 0,
  (next, prev) => {
    if (next > prev && isActive.value) triggerCreditFlash()
  },
)

watch(
  () => avatarDisplay.value?.predicted_ticks ?? 0,
  (next, prev) => {
    if (next > prev && avatarActive.value) triggerAvatarCreditFlash()
  },
)

onBeforeUnmount(() => {
  if (creditFlashTimer !== null) {
    clearTimeout(creditFlashTimer)
    creditFlashTimer = null
  }
  if (avatarFlashTimer !== null) {
    clearTimeout(avatarFlashTimer)
    avatarFlashTimer = null
  }
})

function formatSettleLog(data: {
  settled_ticks: number
  gained_cultivation: number
  gained_body?: number
  gained_crafting?: number
  spent_spirit_stones: number
}): string {
  const parts: string[] = []
  if (data.gained_cultivation) parts.push(`修为 +${data.gained_cultivation}`)
  if (data.gained_body) parts.push(`炼体度 +${data.gained_body}`)
  if (data.gained_crafting) parts.push(`制造业经验 +${data.gained_crafting}`)
  parts.push(`灵石 -${data.spent_spirit_stones}`)
  return `结算 ${data.settled_ticks} 片：${parts.join('，')}`
}

/**
 * 切换到指定方向，或停止。
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
      emit('log', '已停止修炼。', 'info')
      if (data.settled_ticks > 0) {
        emit('log', formatSettleLog(data), 'success')
      }
      return
    }
    const data = await characterStore.setDirection(target)
    const names: Record<string, string> = {
      spirit: '修灵',
      body: '炼体',
      crafting: '制造业',
    }
    emit('log', `开始${names[target] ?? target}。`, 'success')
    if (data.settled_ticks > 0) {
      emit('log', formatSettleLog(data), 'success')
    }
    if (data.character.is_stalled) {
      emit('log', '灵石不足，修炼停滞；可通过战斗获取灵石。', 'warning')
      ElMessage.warning('灵石不足，修炼停滞')
    }
  } catch (e: unknown) {
    const err = e as Error & { code?: number }
    if (err.code === 40030) {
      ElMessage.warning(err.message || '请先领取离线收益')
      emit('needClaimOffline')
      emit('log', err.message, 'warning')
      return
    }
    const message = e instanceof Error ? e.message : '修炼操作失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never" class="idle-panel">
    <template #header>
      <el-text tag="b">修炼区</el-text>
    </template>

    <template v-if="character">
      <!-- —— 本体线程 —— -->
      <div class="thread-block">
        <div class="thread-title">
          <el-text tag="b" size="small">本体</el-text>
          <el-tag size="small" type="info">{{ character.idle_direction_name }}</el-tag>
        </div>

        <el-descriptions :column="1" size="small" class="idle-desc">
          <el-descriptions-item label="预估速度">
            <template v-if="isActive">
              每 {{ character.idle_tick_seconds }}s：{{ poolGainLabel }}
              <template v-if="(character.idle_stones_per_tick ?? 0) > 0">
                / 灵石 -{{ character.idle_stones_per_tick }}
              </template>
              <template v-else> / 不耗灵石</template>
            </template>
            <template v-else>—</template>
          </el-descriptions-item>
          <el-descriptions-item v-if="display && isActive" label="实时推算">
            修为池 {{ display.cultivation_points }} · 炼体
            {{ display.body_tempering_points }} · 制造业 {{ display.crafting_exp }} · 灵石
            {{ display.spirit_stones }}
          </el-descriptions-item>
        </el-descriptions>

        <IdleEnvPanel
          :idle-env="character.idle_env"
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
              本片预计（实时环境）：{{ poolGainLabel }}
            </el-text>
            <el-text v-if="creditFlash" size="small" type="success" class="idle-tick-flash">
              本片收益已并入池
            </el-text>
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

        <el-alert
          v-if="isActive"
          :title="`当前：${modeLabel} — 请先停止修炼后再开战/炼丹炼器/突破/渡劫`"
          type="success"
          show-icon
          :closable="false"
          class="idle-stall"
        />

        <div class="idle-actions">
          <el-button
            :type="direction === 'spirit' ? 'primary' : 'default'"
            :loading="busy"
            :disabled="startDisabled('spirit')"
            @click="setDirection('spirit')"
          >
            {{ direction === 'spirit' ? '停止修灵' : '修灵' }}
          </el-button>
          <el-button
            :type="direction === 'body' ? 'primary' : 'default'"
            :loading="busy"
            :disabled="startDisabled('body')"
            @click="setDirection('body')"
          >
            {{ direction === 'body' ? '停止炼体' : '炼体' }}
          </el-button>
          <el-button
            :type="direction === 'crafting' ? 'primary' : 'default'"
            :loading="busy"
            :disabled="startDisabled('crafting')"
            @click="setDirection('crafting')"
          >
            {{ direction === 'crafting' ? '停止制造业' : '制造业' }}
          </el-button>
          <el-button
            v-if="isActive"
            :loading="busy"
            :disabled="hasPending"
            @click="setDirection(direction as IdleDirection)"
          >
            停止修炼
          </el-button>
        </div>
      </div>

      <!-- —— 化身线程（只读进度；切方向去化身页） —— -->
      <div v-if="hasAvatar" class="thread-block avatar-thread">
        <div class="thread-title">
          <el-text tag="b" size="small">化身</el-text>
          <el-tag size="small" type="warning">
            {{ directionNames[avatarDirection] ?? avatarDirection }}
          </el-tag>
          <el-button size="small" text type="primary" @click="router.push('/avatar')">
            管理
          </el-button>
        </div>

        <el-descriptions :column="1" size="small" class="idle-desc">
          <el-descriptions-item label="预估速度">
            <template v-if="avatarActive">
              每 {{ character.idle_tick_seconds }}s：{{ avatarPoolGainLabel }}
              <template v-if="avatarStonesPerTick > 0">
                / 灵石 -{{ avatarStonesPerTick }}
              </template>
              <template v-else> / 不耗灵石</template>
            </template>
            <template v-else>待机（去化身页安排方向）</template>
          </el-descriptions-item>
          <el-descriptions-item v-if="avatarDisplay && avatarActive" label="实时推算">
            修为池 {{ avatarDisplay.cultivation_points }} · 炼体
            {{ avatarDisplay.body_tempering_points }} · 制造业
            {{ avatarDisplay.crafting_exp }}
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="avatarActive && avatarDisplay" class="idle-tick idle-tick-avatar">
          <div class="idle-tick-label">
            <el-text size="small">化身本回合</el-text>
            <el-text size="small" type="info">
              <template v-if="avatarShowStalled || hasPending">已暂停</template>
              <template v-else-if="avatarSecondsLeft != null">
                还剩 {{ avatarSecondsLeft }}s
              </template>
            </el-text>
          </div>
          <el-progress
            :percentage="avatarShowStalled || hasPending ? 0 : avatarTickPercent"
            :stroke-width="12"
            color="#e6a23c"
            :striped="avatarActive && !avatarShowStalled && !hasPending"
            :striped-flow="avatarActive && !avatarShowStalled && !hasPending"
            :status="avatarCreditFlash ? 'success' : undefined"
          />
          <div class="idle-tick-meta">
            <el-text size="small" type="info">
              本片预计（实时环境）：{{ avatarPoolGainLabel }}
            </el-text>
            <el-text
              v-if="avatarCreditFlash"
              size="small"
              type="success"
              class="idle-tick-flash"
            >
              化身本片收益已并入池
            </el-text>
          </div>
        </div>

        <el-alert
          v-if="avatarShowStalled && avatarActive"
          title="灵石不足，化身线程停滞（与本体共享灵石池）"
          type="warning"
          show-icon
          :closable="false"
          class="idle-stall"
        />
      </div>

      <el-alert
        v-else
        title="金丹后可凝练化身，并行挂机进度将显示于此"
        type="info"
        :closable="false"
        class="idle-stall"
      >
        <el-button size="small" text type="primary" @click="router.push('/avatar')">
          前往化身
        </el-button>
      </el-alert>

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
  </el-card>
</template>

<style scoped>
.thread-block {
  margin-bottom: 0.85rem;
}

.thread-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.35rem;
}

.avatar-thread {
  padding-top: 0.75rem;
  border-top: 1px dashed rgba(230, 162, 60, 0.45);
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

.idle-tick-avatar {
  background: linear-gradient(180deg, rgba(230, 162, 60, 0.12), transparent);
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
  flex-wrap: wrap;
  gap: 0.5rem;
}
</style>
