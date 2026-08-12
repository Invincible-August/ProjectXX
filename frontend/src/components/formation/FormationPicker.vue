<script setup lang="ts">
/**
 * 阵法下拉：未解锁显示锁与 required_array_level 提示。
 */
import { computed } from 'vue'
import type { FormationInfo } from '../../types/formation'

const props = defineProps<{
  formations: FormationInfo[]
  modelValue: string
  arrayCraftLevel?: number
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

/** 当前选中阵法 */
const current = computed(() =>
  props.formations.find((f) => f.formation_id === props.modelValue),
)

function optionLabel(formation: FormationInfo): string {
  const base = `${formation.name}（Lv.${formation.level}）`
  if (formation.unlocked) return base
  const req = formation.required_array_level ?? 0
  if (req > 0) return `${base} 🔒 需阵法${req}级`
  return `${base} 🔒`
}
</script>

<template>
  <div class="formation-picker-wrap">
    <el-select
      :model-value="modelValue"
      size="small"
      class="formation-picker"
      @update:model-value="(v: string) => emit('update:modelValue', v)"
    >
      <el-option
        v-for="formation in formations"
        :key="formation.formation_id"
        :value="formation.formation_id"
        :label="optionLabel(formation)"
        :disabled="!formation.unlocked"
      />
    </el-select>
    <el-text
      v-if="current && !current.unlocked && (current.required_array_level ?? 0) > 0"
      type="warning"
      size="small"
      class="lock-hint"
    >
      阵法等级不足（当前 {{ arrayCraftLevel ?? 0 }} / 需 {{ current.required_array_level }}）· 工坊钻研阵法
    </el-text>
  </div>
</template>

<style scoped>
.formation-picker-wrap {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.formation-picker {
  min-width: 180px;
}

.lock-hint {
  max-width: 280px;
  line-height: 1.3;
}
</style>
