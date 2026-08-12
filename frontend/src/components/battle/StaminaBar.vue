<script setup lang="ts">
/**
 * 体力条：常驻 /battle 与大厅入口卡片。
 *
 * 显示当前体力 / 上限 / 恢复倒计时；本地按 next_point_in_seconds 递减模拟，
 * 到点后 +1 并按恢复速率重置倒计时（权威值以开战响应 / fetchStamina 为准）。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useBattleStore } from '../../stores/battle'

const battleStore = useBattleStore()
const localCountdown = ref(0)
let ticker: ReturnType<typeof setInterval> | null = null

const stamina = computed(() => battleStore.stamina)

/** 进度条百分比 */
const percent = computed(() => {
  if (!stamina.value || stamina.value.cap <= 0) return 0
  return Math.round((stamina.value.left / stamina.value.cap) * 100)
})

/** 每恢复 1 点所需秒数（由速率折算） */
const secondsPerPoint = computed(() => {
  const rate = stamina.value?.regen_per_minute ?? 0
  return rate > 0 ? Math.round(60 / rate) : 0
})

watch(
  () => stamina.value?.next_point_in_seconds,
  (value) => {
    localCountdown.value = value ?? 0
  },
  { immediate: true },
)

onMounted(() => {
  void battleStore.refreshStamina()
  ticker = setInterval(() => {
    if (!stamina.value) return
    if (stamina.value.left >= stamina.value.cap) return
    if (localCountdown.value > 1) {
      localCountdown.value -= 1
    } else if (secondsPerPoint.value > 0) {
      // 本地模拟恢复 1 点；权威值下次接口响应校正
      stamina.value.left = Math.min(stamina.value.cap, stamina.value.left + 1)
      localCountdown.value = secondsPerPoint.value
    }
  }, 1000)
})

onUnmounted(() => {
  if (ticker) clearInterval(ticker)
})
</script>

<template>
  <div class="stamina-bar">
    <el-text tag="b" size="small">体力</el-text>
    <el-progress
      :percentage="percent"
      :stroke-width="14"
      class="stamina-progress"
      :format="() => (stamina ? `${stamina.left}/${stamina.cap}` : '—')"
    />
    <el-text v-if="stamina && stamina.left < stamina.cap" type="info" size="small">
      {{ localCountdown }} 秒后恢复 1 点
    </el-text>
  </div>
</template>

<style scoped>
.stamina-bar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.stamina-progress {
  flex: 1;
  min-width: 160px;
}
</style>
