<script setup lang="ts">
/**
 * 全局世界时钟顶栏：时辰倒计时 + 天气；悬停时辰查看说明。
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

const catalogShichen = computed(() => env.value?.catalog?.shichen ?? null)
const catalogWeather = computed(() => env.value?.catalog?.weather ?? null)

const hintLines = computed(() => {
  const h = env.value?.hints
  if (!h) return [] as { label: string; text: string }[]
  return [
    h.idle ? { label: '挂机', text: h.idle } : null,
    h.breakthrough ? { label: '突破', text: h.breakthrough } : null,
    h.craft ? { label: '工坊', text: h.craft } : null,
    h.tribulation ? { label: '渡劫', text: h.tribulation } : null,
  ].filter((x): x is { label: string; text: string } => Boolean(x))
})

const hasShichenTip = computed(() => {
  const s = catalogShichen.value
  const w = catalogWeather.value
  return Boolean(
    s?.summary ||
      s?.idle_note ||
      s?.spawn_bias_note ||
      s?.breakthrough_note ||
      w?.summary ||
      w?.idle_note ||
      w?.breakthrough_note ||
      w?.tribulation_note ||
      hintLines.value.length ||
      env.value?.calendar_enabled === false,
  )
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
        <el-popover
          placement="bottom-start"
          :width="360"
          trigger="hover"
          :disabled="!hasShichenTip"
          popper-class="world-shichen-popper"
        >
          <template #reference>
            <el-text tag="b" class="shichen shichen-hot">
              {{ shichenText || '历法校准中' }}
            </el-text>
          </template>
          <div class="tip-body">
            <div v-if="catalogShichen" class="tip-block">
              <el-text tag="b" size="small">
                {{ catalogShichen.label || shichenText }}
              </el-text>
              <el-text v-if="catalogShichen.summary" size="small" class="tip-line">
                {{ catalogShichen.summary }}
              </el-text>
              <el-text
                v-if="catalogShichen.idle_note"
                size="small"
                type="success"
                class="tip-line"
              >
                修炼：{{ catalogShichen.idle_note }}
              </el-text>
              <el-text
                v-if="catalogShichen.spawn_bias_note"
                size="small"
                type="warning"
                class="tip-line"
              >
                妖兽：{{ catalogShichen.spawn_bias_note }}
              </el-text>
              <el-text
                v-if="catalogShichen.breakthrough_note"
                size="small"
                type="info"
                class="tip-line"
              >
                突破：{{ catalogShichen.breakthrough_note }}
              </el-text>
            </div>

            <el-divider v-if="catalogShichen && catalogWeather" />

            <div v-if="catalogWeather" class="tip-block">
              <el-text tag="b" size="small">
                {{ catalogWeather.label || weatherText }}
              </el-text>
              <el-text v-if="catalogWeather.summary" size="small" class="tip-line">
                {{ catalogWeather.summary }}
              </el-text>
              <el-text
                v-if="catalogWeather.idle_note"
                size="small"
                type="success"
                class="tip-line"
              >
                修炼：{{ catalogWeather.idle_note }}
              </el-text>
              <el-text
                v-if="catalogWeather.breakthrough_note"
                size="small"
                type="info"
                class="tip-line"
              >
                突破：{{ catalogWeather.breakthrough_note }}
              </el-text>
              <el-text
                v-if="catalogWeather.tribulation_note"
                size="small"
                type="warning"
                class="tip-line"
              >
                渡劫：{{ catalogWeather.tribulation_note }}
              </el-text>
            </div>

            <template v-if="hintLines.length">
              <el-divider v-if="catalogShichen || catalogWeather" />
              <div
                v-for="line in hintLines"
                :key="line.label"
                class="tip-line"
              >
                <el-text size="small" type="info">
                  {{ line.label }}：{{ line.text }}
                </el-text>
              </div>
            </template>

            <el-text
              v-if="env?.calendar_enabled === false"
              size="small"
              type="warning"
              class="tip-line"
            >
              历法校准中（固定正午）· DEV
            </el-text>
          </div>
        </el-popover>

        <el-text size="small" type="info">
          距下一时 {{ worldStore.countdownLabel }}
        </el-text>
        <el-text size="small" class="weather">
          <span class="weather-icon" aria-hidden="true">{{ weatherEmoji }}</span>
          天气：{{ weatherText }}
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
      </div>
    </Transition>
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

.shichen-hot {
  cursor: help;
  border-bottom: 1px dashed rgba(64, 158, 255, 0.55);
  padding-bottom: 1px;
}

.weather {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

.weather-icon {
  font-size: 1rem;
}

.ferry-badge {
  cursor: pointer;
  animation: ferry-pulse 1.4s ease-in-out infinite;
}

.tip-body {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.tip-block {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.tip-line {
  display: block;
  line-height: 1.45;
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
