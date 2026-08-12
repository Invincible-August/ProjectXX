<script setup lang="ts">
/**
 * 战斗页开战锁定环境预览行。
 */
import { computed } from 'vue'
import { useCharacterStore } from '../../stores/character'
import { useWorldStore } from '../../stores/world'
import { shichenLabel } from '../../utils/shichenLabel'
import { weatherLabel } from '../../utils/weatherIcon'

const props = defineProps<{
  /** 战报/开战响应中的锁定字段（可选） */
  lockedShichen?: string | null
  lockedShichenLabel?: string | null
  lockedWeather?: string | null
  lockedWeatherLabel?: string | null
}>()

const worldStore = useWorldStore()
const characterStore = useCharacterStore()

const statusBlocked = computed(() => {
  const s = characterStore.character?.status
  return s === 'tribulation' || s === 'awaiting_ferry' || s === 'reincarnating'
})

const statusTip = computed(() => {
  const s = characterStore.character?.status
  if (s === 'tribulation') return '渡劫中不可开战'
  if (s === 'awaiting_ferry') return '待引渡中不可开战'
  if (s === 'reincarnating') return '轮回结算中不可开战'
  return ''
})

const previewLine = computed(() => {
  // 仅作「此刻预览」：真正锁定发生在点击开战那一请求瞬间，不是进页那一刻
  const shichen =
    props.lockedShichenLabel ||
    shichenLabel(props.lockedShichen || worldStore.env?.shichen, worldStore.env?.shichen_label)
  const weather =
    props.lockedWeatherLabel ||
    weatherLabel(props.lockedWeather || worldStore.env?.weather, worldStore.env?.weather_label)
  if (props.lockedShichen || props.lockedWeather) {
    return `本场已锁定（开战瞬间）：${shichen} · ${weather}`
  }
  return `预览当前环境（点「开战」瞬间才锁定，进页不锁）：${shichen} · ${weather}`
})
</script>

<template>
  <div class="battle-env-lock">
    <el-alert
      v-if="statusBlocked"
      :title="statusTip"
      type="warning"
      show-icon
      :closable="false"
    />
    <el-text v-else size="small" type="info">{{ previewLine }}</el-text>
  </div>
</template>

<style scoped>
.battle-env-lock {
  margin: 0.5rem 0;
}
</style>
