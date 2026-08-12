<script setup lang="ts">
/**
 * 预设三槽切换条：展示 role/name；切槽时若草稿脏则由父组件确认。
 */
import type { FormationPreset } from '../../types/formation'

defineProps<{
  presets: FormationPreset[]
  activeSlot: number
}>()

const emit = defineEmits<{
  select: [slot: number]
}>()

/** 定位 → 中文标签 */
const ROLE_LABELS: Record<string, string> = {
  attack: '进攻',
  defense: '防守',
  temp: '临时',
}
</script>

<template>
  <div class="preset-bar">
    <el-button
      v-for="preset in presets"
      :key="preset.slot"
      :type="preset.slot === activeSlot ? 'primary' : 'default'"
      size="small"
      @click="emit('select', preset.slot)"
    >
      [{{ ROLE_LABELS[preset.role] ?? preset.role }}] {{ preset.name }}
    </el-button>
  </div>
</template>

<style scoped>
.preset-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
</style>
