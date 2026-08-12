<script setup lang="ts">
/**
 * 灵宠列表（不可替代本体提示）。
 */
import type { PetPublic } from '../../types/pets'
import { petDisplayName } from '../../utils/petDisplay'

defineProps<{
  pets: PetPublic[]
  focusId?: number | null
}>()

const emit = defineEmits<{
  select: [pet: PetPublic]
}>()

</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">灵兽园</el-text>
    </template>

    <el-text type="info" size="small" class="hint">灵宠不可替代本体上阵。</el-text>

    <el-empty v-if="pets.length === 0" description="尚无灵宠" :image-size="48" />

    <div
      v-for="pet in pets"
      :key="pet.id"
      class="pet-row"
      :class="{ focused: focusId === pet.id }"
      @click="emit('select', pet)"
    >
      <el-text tag="b" size="small">{{ petDisplayName(pet) }}</el-text>
      <el-tag size="small">Lv.{{ pet.level }}</el-tag>
      <el-tag v-if="pet.grade_name || pet.grade" size="small" type="warning">
        {{ pet.grade_name || `品阶${pet.grade}` }}
      </el-tag>
      <el-tag v-if="pet.race_name || pet.race" size="small">
        {{ pet.race_name || pet.race }}
      </el-tag>
      <el-tag v-if="pet.rarity" size="small" type="info">{{ pet.rarity }}</el-tag>
      <el-tag v-if="pet.is_deploy_preferred" size="small" type="success">偏好上阵</el-tag>
      <el-text v-if="pet.stats" size="small" type="info">
        攻{{ pet.stats.atk }}/血{{ pet.stats.hp }}
      </el-text>
    </div>
  </el-card>
</template>

<style scoped>
.hint {
  display: block;
  margin-bottom: 0.5rem;
}

.pet-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  margin-bottom: 0.35rem;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.pet-row:hover,
.pet-row.focused {
  background: rgba(64, 158, 255, 0.08);
}
</style>
