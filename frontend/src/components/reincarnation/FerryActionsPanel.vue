<script setup lang="ts">
/**
 * 待引渡操作：自救 / 求援社交引渡 / 进入轮回。
 * 自救消耗与不可用原因必须显性展示（灵石 / 冷却）。
 * 道友/同门引渡由救援者在 /social?mode=ferry 发起并支付。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useCharacterStore } from '../../stores/character'
import { useFerryStore } from '../../stores/ferry'

const router = useRouter()

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
  rescued: []
  reincarnated: []
}>()

const ferryStore = useFerryStore()
const characterStore = useCharacterStore()
const busy = ref(false)
/** 本地倒计时刷新，冷却秒数会往下走 */
const tick = ref(0)
let tickTimer: ReturnType<typeof setInterval> | null = null

const ferry = computed(() => ferryStore.ferry)

const cost = computed(() => ferry.value?.self_rescue_cost ?? 500)
const costLabel = computed(() => ferry.value?.self_rescue_cost_label || '灵石')
const currentStones = computed(
  () =>
    ferry.value?.spirit_stones ??
    characterStore.character?.spirit_stones ??
    0,
)

/** 社交引渡成本对照（待引渡本人也可看见，方便喊价求援） */
const socialCosts = computed(
  () => ferry.value?.social_rescue ?? ferryStore.socialRescueCosts,
)

function goSocialFerry(): void {
  void router.push({ path: '/social', query: { mode: 'ferry' } })
}

/** 上次从服务端拿到的冷却剩余与本地时刻，用于秒级递减展示 */
const cooldownSnapshot = ref({ seconds: 0, atMs: 0 })

watch(
  () => ferry.value?.self_rescue_cooldown_seconds,
  (seconds) => {
    cooldownSnapshot.value = {
      seconds: Math.max(0, Number(seconds) || 0),
      atMs: Date.now(),
    }
  },
  { immediate: true },
)

/** 冷却剩余（本地递减，定期用 loadFerry 校准） */
const cooldownLeft = computed(() => {
  void tick.value
  const { seconds, atMs } = cooldownSnapshot.value
  if (seconds <= 0 || atMs <= 0) return 0
  const elapsed = Math.floor((Date.now() - atMs) / 1000)
  return Math.max(0, seconds - elapsed)
})

const blockReason = computed(() => {
  if (ferry.value?.can_self_rescue) return ''
  return (
    ferry.value?.self_rescue_reason ||
    (cooldownLeft.value > 0
      ? `自救冷却中（还需 ${cooldownLeft.value} 秒）`
      : currentStones.value < cost.value
        ? `灵石不足（自救需 ${cost.value} 灵石，当前 ${currentStones.value}）`
        : '当前不可自救')
  )
})

const rescueButtonText = computed(
  () => `自救（消耗 ${cost.value} ${costLabel.value}）`,
)

onMounted(() => {
  tickTimer = setInterval(() => {
    tick.value += 1
    // 冷却中每 5 秒向服务器校准一次剩余与 can_self_rescue
    if (tick.value % 5 === 0 && (ferry.value?.self_rescue_cooldown_seconds ?? 0) > 0) {
      void ferryStore.loadFerry()
    }
  }, 1_000)
})

onBeforeUnmount(() => {
  if (tickTimer != null) {
    clearInterval(tickTimer)
    tickTimer = null
  }
})

async function onSelfRescue(): Promise<void> {
  if (busy.value) return
  if (!ferry.value?.can_self_rescue) {
    ElMessage.warning(blockReason.value || '当前不可自救')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认自救？将消耗 ${cost.value} ${costLabel.value}（当前持有 ${currentStones.value}）。\n` +
        `自救后有冷却，短时间内再次陨落可能暂时无法自救。`,
      '自救确认',
      { type: 'warning', confirmButtonText: '确认自救', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  busy.value = true
  try {
    const err = await ferryStore.doSelfRescue()
    if (err) throw new Error(err)
    ElMessage.success(ferryStore.lastMessage || '自救成功')
    emit('log', ferryStore.lastMessage || '自救成功', 'success')
    emit('rescued')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '自救失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function onEnter(): Promise<void> {
  if (busy.value) return
  if (!ferryStore.preview) {
    const err = await ferryStore.loadPreview('voluntary_ferry')
    if (err) {
      ElMessage.error(err)
      return
    }
  }
  try {
    await ElMessageBox.confirm(
      '确认进入轮回？境界将重置，快照作废，化身解散；体质与道号保留。结算后进入新生选角（灵根/传承/商店）。',
      '进入轮回',
      { type: 'warning', confirmButtonText: '确认轮回', cancelButtonText: '再想想' },
    )
  } catch {
    return
  }
  busy.value = true
  try {
    const err = await ferryStore.enter()
    if (err) throw new Error(err)
    ElMessage.success(ferryStore.lastMessage || '轮回完成')
    emit('log', ferryStore.lastMessage || '轮回完成', 'success')
    emit('reincarnated')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '进入轮回失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">引渡抉择</el-text>
    </template>

    <el-descriptions :column="1" size="small" border class="cost-desc">
      <el-descriptions-item label="自救消耗">
        {{ cost }} {{ costLabel }}（当前持有 {{ currentStones }} {{ costLabel }}）
      </el-descriptions-item>
      <el-descriptions-item v-if="socialCosts" label="求援对照">
        道友引渡 {{ socialCosts.friend_cost }} / 同门 {{ socialCosts.sect_cost }}
        {{ costLabel }}（由救援者支付，低于自救）
      </el-descriptions-item>
      <el-descriptions-item
        v-if="(ferry?.self_rescue_cooldown_total_seconds ?? 0) > 0"
        label="自救冷却"
      >
        配置 {{ ferry?.self_rescue_cooldown_total_seconds }} 秒
        <template v-if="cooldownLeft > 0">
          · 剩余 {{ cooldownLeft }} 秒
        </template>
        <template v-else> · 当前可用</template>
      </el-descriptions-item>
    </el-descriptions>

    <el-alert
      v-if="blockReason"
      :title="blockReason"
      type="warning"
      show-icon
      :closable="false"
      class="block-hint"
    />

    <div class="actions">
      <el-button
        type="success"
        :disabled="!ferry?.can_self_rescue"
        :loading="busy"
        @click="onSelfRescue"
      >
        {{ rescueButtonText }}
      </el-button>

      <el-tooltip
        content="请道友/同门在「社交 → 引渡」发起；由对方支付较低灵石"
        placement="top"
      >
        <el-button type="primary" plain @click="goSocialFerry">去求援</el-button>
      </el-tooltip>

      <el-button type="danger" :loading="busy" @click="onEnter">进入轮回</el-button>
    </div>
  </el-card>
</template>

<style scoped>
.cost-desc {
  margin-bottom: 0.65rem;
}

.block-hint {
  margin-bottom: 0.65rem;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
</style>
