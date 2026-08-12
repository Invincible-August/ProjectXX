<script setup lang="ts">
/**
 * 工坊开工天气提示一行。
 */
import { computed } from 'vue'
import { useWorldStore } from '../../stores/world'
import { weatherIcon, weatherLabel } from '../../utils/weatherIcon'

const worldStore = useWorldStore()

const line = computed(() => {
  const env = worldStore.env
  if (!env) return ''
  const w = weatherLabel(env.weather, env.weather_label)
  const icon = weatherIcon(env.weather)
  const hint = env.hints.craft
  return hint
    ? `${icon} 当前将锁定天气：${w} · ${hint}`
    : `${icon} 当前将锁定天气：${w}`
})
</script>

<template>
  <el-text v-if="line" size="small" type="info" class="craft-env-hint">
    {{ line }}
  </el-text>
</template>

<style scoped>
.craft-env-hint {
  display: block;
  margin: 0.35rem 0;
}
</style>
