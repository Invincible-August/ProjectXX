<script setup lang="ts">
/**
 * 双线程挂机速率一行摘要：本体 ∥ 化身（只读，来自 character.dual_idle_preview）。
 */
import { computed } from 'vue'
import { useCharacterStore } from '../../stores/character'

const characterStore = useCharacterStore()

const preview = computed(() => characterStore.character?.dual_idle_preview)

const mainLabel = computed(() => {
  const ch = characterStore.character
  if (!ch) return '—'
  const dir = preview.value?.main_idle_direction ?? ch.idle_direction
  if (dir === 'spirit') {
    const rate = preview.value?.main_cultivation_per_tick ?? ch.idle_cultivation_per_tick
    return `本体修灵 +${rate}/片`
  }
  if (dir === 'body') {
    const rate = preview.value?.main_body_per_tick ?? ch.idle_body_per_tick ?? 0
    return `本体炼体 +${rate}/片`
  }
  if (dir === 'crafting') {
    const rate = preview.value?.main_crafting_per_tick ?? ch.idle_crafting_per_tick ?? 0
    return `本体制造业 +${rate}/片`
  }
  return '本体待机'
})

const avatarLabel = computed(() => {
  const ch = characterStore.character
  if (!ch?.has_avatar) return '化身未凝练'
  const dir = preview.value?.avatar_idle_direction ?? ch.avatar_summary?.idle_direction ?? 'none'
  if (dir === 'spirit') {
    const rate = preview.value?.avatar_cultivation_per_tick ?? 0
    return `化身修灵 +${rate}/片`
  }
  if (dir === 'body') {
    const rate = preview.value?.avatar_body_per_tick ?? 0
    return `化身炼体 +${rate}/片`
  }
  if (dir === 'crafting') {
    const rate = preview.value?.avatar_crafting_per_tick ?? 0
    return `化身制造业 +${rate}/片`
  }
  if (dir === 'none') return '化身待机'
  return `化身 ${dir}`
})
</script>

<template>
  <el-card v-if="characterStore.character" shadow="never" class="dual-summary">
    <el-text size="small" type="info">
      {{ mainLabel }} ∥ {{ avatarLabel }}
    </el-text>
  </el-card>
</template>

<style scoped>
.dual-summary {
  padding: 0.25rem 0;
}

.dual-summary :deep(.el-card__body) {
  padding: 0.5rem 0.75rem;
}
</style>
