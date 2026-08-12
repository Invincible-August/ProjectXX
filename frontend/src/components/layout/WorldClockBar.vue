<script setup lang="ts">
/**
 * 全局世界时钟顶栏：时辰倒计时 + 天气 + 行为提示；待引渡角标。
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useCharacterStore } from '../../stores/character'
import { useWorldStore } from '../../stores/world'
import { shichenLabel } from '../../utils/shichenLabel'
import { weatherIcon, weatherLabel } from '../../utils/weatherIcon'

const router = useRouter()
const worldStore = useWorldStore()
const characterStore = useCharacterStore()

const detailsOpen = ref(false)
/** 时辰切换淡入 key */
const fadeKey = ref(0)

const env = computed(() => worldStore.env)
const awaitingFerry = computed(
  () => characterStore.character?.status === 'awaiting_ferry',
)

const shichenText = computed(() =>
  shichenLabel(env.value?.shichen, env.value?.shichen_label),
)
const weatherText = computed(() =>
  weatherLabel(env.value?.weather, env.value?.weather_label),
)
const weatherEmoji = computed(() => weatherIcon(env.value?.weather))

const hintLine = computed(() => {
  const h = env.value?.hints
  if (!h) return ''
  return [h.tribulation, h.craft, h.idle, h.breakthrough].filter(Boolean).join(' · ')
})

watch(
  () => env.value?.shichen,
  (next, prev) => {
    if (prev && next && prev !== next) fadeKey.value += 1
  },
)
</script>

<template>
  <div class="world-bar">
    <Transition name="shichen-fade" mode="out-in">
      <div :key="fadeKey" class="world-bar-main">
        <el-text tag="b" class="shichen">
          {{ shichenText || '历法校准中' }}
        </el-text>
        <el-text size="small" type="info">
          距下一时 {{ worldStore.countdownLabel }}
        </el-text>
        <el-text size="small" class="weather">
          <span class="weather-icon" aria-hidden="true">{{ weatherEmoji }}</span>
          天气：{{ weatherText }}
        </el-text>
        <el-text v-if="hintLine" size="small" type="warning" class="hint" truncated>
          提示：{{ hintLine }}
        </el-text>
        <el-tag
          v-if="awaitingFerry"
          type="danger"
          effect="dark"
          size="small"
          class="ferry-badge"
          @click="router.push('/reincarnation?mode=ferry')"
        >
          待引渡
        </el-tag>
        <el-button text size="small" type="primary" @click="detailsOpen = !detailsOpen">
          {{ detailsOpen ? '收起' : '详情' }}
        </el-button>
      </div>
    </Transition>

    <div v-if="detailsOpen && env" class="world-bar-details">
      <el-text size="small" type="info">挂机：{{ env.hints.idle || '—' }}</el-text>
      <el-text size="small" type="info">突破：{{ env.hints.breakthrough || '—' }}</el-text>
      <el-text size="small" type="info">工坊：{{ env.hints.craft || '—' }}</el-text>
      <el-text size="small" type="info">渡劫：{{ env.hints.tribulation || '—' }}</el-text>
      <el-text
        v-if="env.calendar_enabled === false"
        size="small"
        type="warning"
      >
        历法校准中（固定正午）· DEV
      </el-text>
    </div>
  </div>
</template>

<style scoped>
.world-bar {
  background: linear-gradient(90deg, #f0f5fa 0%, #e8eef6 50%, #f5f0ea 100%);
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 0.4rem 1rem;
}

.world-bar-main {
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.85rem;
}

.shichen {
  letter-spacing: 0.05em;
}

.weather {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

.weather-icon {
  font-size: 1rem;
}

.hint {
  max-width: 280px;
}

.ferry-badge {
  cursor: pointer;
  animation: ferry-pulse 1.4s ease-in-out infinite;
}

.world-bar-details {
  max-width: 1100px;
  margin: 0.35rem auto 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
}

.shichen-fade-enter-active,
.shichen-fade-leave-active {
  transition: opacity 0.35s ease;
}

.shichen-fade-enter-from,
.shichen-fade-leave-to {
  opacity: 0;
}

@keyframes ferry-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.65;
  }
}
</style>
