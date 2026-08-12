<script setup lang="ts">
/**
 * 道主开窗横幅：开放中 / 倒计时；到点由父级 refresh。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type { DaoLordWindowPublic } from '../../types/daoLord'

const props = defineProps<{
  window: DaoLordWindowPublic | null
}>()

const emit = defineEmits<{
  expired: []
}>()

const nowMs = ref(Date.now())
let tickTimer: ReturnType<typeof setInterval> | null = null

const countdownTarget = computed(() => {
  const w = props.window
  if (!w) return null
  if (w.open && w.closes_at) return w.closes_at
  if (!w.open && w.next_open_at) return w.next_open_at
  return null
})

const countdownLabel = computed(() => {
  void nowMs.value
  const target = countdownTarget.value
  if (!target) return ''
  const left = Date.parse(target) - Date.now()
  if (left <= 0) return '0:00'
  const totalSec = Math.floor(left / 1000)
  const m = Math.floor(totalSec / 60)
  const s = totalSec % 60
  return `${m}:${String(s).padStart(2, '0')}`
})

const bannerTitle = computed(() => {
  const w = props.window
  if (!w) return '开窗信息加载中…'
  if (w.open) return `挑战开放中 · ${w.label}`
  return `非挑战时段 · ${w.label}`
})

onMounted(() => {
  tickTimer = setInterval(() => {
    nowMs.value = Date.now()
    const target = countdownTarget.value
    if (target && Date.parse(target) <= Date.now()) {
      emit('expired')
    }
  }, 1000)
})

onUnmounted(() => {
  if (tickTimer) clearInterval(tickTimer)
})

watch(
  () => props.window?.open,
  () => {
    nowMs.value = Date.now()
  },
)
</script>

<template>
  <el-alert
    class="window-banner"
    :type="window?.open ? 'success' : 'warning'"
    :closable="false"
    show-icon
  >
    <template #title>
      <span>{{ bannerTitle }}</span>
      <span v-if="countdownLabel" class="cd">
        {{ window?.open ? '距关闭' : '距开放' }} {{ countdownLabel }}
      </span>
    </template>
  </el-alert>
</template>

<style scoped>
.window-banner {
  margin-bottom: 0.75rem;
}

.cd {
  margin-left: 0.75rem;
  font-variant-numeric: tabular-nums;
  opacity: 0.9;
}
</style>
