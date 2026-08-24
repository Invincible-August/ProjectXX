<script setup lang="ts">
/**
 * 阵法预设下拉：按自定义名称选槽编辑；切槽确认由父组件处理。
 */
import type { FormationPreset } from '../../types/formation'

defineProps<{
  presets: FormationPreset[]
  activeSlot: number
}>()

const emit = defineEmits<{
  select: [slot: number]
}>()

function optionLabel(preset: FormationPreset): string {
  const name = preset.name.trim()
  return name || `阵法${preset.slot + 1}`
}
</script>

<template>
  <el-select
    class="preset-select"
    size="small"
    :model-value="activeSlot"
    @update:model-value="(value: number) => emit('select', value)"
  >
    <el-option
      v-for="preset in presets"
      :key="preset.slot"
      :value="preset.slot"
      :label="optionLabel(preset)"
    />
  </el-select>
</template>

<style scoped>
.preset-select {
  width: 160px;
}
</style>
