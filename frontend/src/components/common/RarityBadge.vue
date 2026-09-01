<script setup lang="ts">
/**
 * Shared rarity badge: solid accent + white Chinese name (粗糙…太古 / domain label).
 * Use on hover tips and detail dialogs — not on dense list chips (those use color only).
 */
import { computed } from 'vue'
import { rarityBadgeStyle, rarityLabelZh } from '../../utils/rarityDisplay'

const props = withDefaults(
  defineProps<{
    rarity: string | null | undefined
    /** Optional API label_zh / rarity_label; color names and English ids are ignored. */
    label?: string | null
    size?: 'small' | 'default'
  }>(),
  { label: null, size: 'small' },
)

const text = computed(() => rarityLabelZh(props.rarity, props.label))
const style = computed(() => rarityBadgeStyle(props.rarity))
</script>

<template>
  <span
    class="rarity-badge"
    :class="{ 'is-default': size === 'default' }"
    :style="style"
  >
    {{ text }}
  </span>
</template>

<style scoped>
.rarity-badge {
  display: inline-flex;
  align-items: center;
  padding: 0.05rem 0.4rem;
  border: 1px solid;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 600;
  line-height: 1.4;
  white-space: nowrap;
}
.rarity-badge.is-default {
  font-size: 0.8rem;
  padding: 0.1rem 0.5rem;
}
</style>
