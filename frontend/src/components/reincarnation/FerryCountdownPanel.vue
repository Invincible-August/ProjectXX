<script setup lang="ts">
/**
 * 待引渡大倒计时；到期触发 refresh（不幻想自救成功）。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  ferryRemainMs,
  formatFerryCountdown,
  isFerryExpired,
} from '../../utils/ferryCountdown'

const props = defineProps<{
  deadlineAt: string | null | undefined
}>()

const emit = defineEmits<{
  expired: []
}>()

const nowMs = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null
let ferryTickMs = 1_000

const remainMs = computed(() => ferryRemainMs(props.deadlineAt, nowMs.value))
const label = computed(() => {
  // 无截止时间：不显示 0:00，避免误触发「已过期」校准风暴
  if (!props.deadlineAt) return '校准中…'
  return formatFerryCountdown(remainMs.value)
})
/** 仅在确有 deadline 且已到期时视为过期 */
const expired = computed(
  () => Boolean(props.deadlineAt) && isFerryExpired(props.deadlineAt, nowMs.value),
)

onMounted(() => {
  const raw = import.meta.env.VITE_FERRY_TICK_MS
  const parsed = raw ? Number(raw) : 1_000
  ferryTickMs = Number.isFinite(parsed) && parsed >= 200 ? parsed : 1_000
  timer = setInterval(() => {
    nowMs.value = Date.now()
  }, ferryTickMs)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

watch(expired, (isExp, was) => {
  if (isExp && !was) emit('expired')
})
</script>

<template>
  <el-card shadow="never" class="ferry-countdown">
    <template #header>
      <el-text tag="b">待引渡倒计时</el-text>
    </template>
    <div class="clock" :class="{ pulse: !expired && deadlineAt, expired }">
      {{ label }}
    </div>
    <el-text v-if="!deadlineAt" type="info" size="small">
      正在拉取引渡截止时间…
    </el-text>
    <el-text v-else-if="expired" type="danger" size="small">
      时限已至，正在与服务器校准…
    </el-text>
    <el-text v-else type="info" size="small">
      倒计时归零将强制进入轮回；请尽快自救或自选轮回。
    </el-text>
  </el-card>
</template>

<style scoped>
.clock {
  font-size: 2.4rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  font-variant-numeric: tabular-nums;
  margin: 0.5rem 0 0.75rem;
  color: var(--el-color-danger);
}

.clock.pulse {
  animation: countdown-pulse 1.2s ease-in-out infinite;
}

.clock.expired {
  opacity: 0.7;
  animation: none;
}

@keyframes countdown-pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.03);
    opacity: 0.85;
  }
}
</style>
