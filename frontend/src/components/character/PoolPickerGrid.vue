<script setup lang="ts">
/**
 * Compact wrap grid for learned/collection pickers (not one full-width row per item).
 * §0.0.4: ItemSlotVisual (icon or full name); rarity chips when rarity set.
 */
import type { PoolCandidate } from '../../types/itemHover'
import { rarityChipStyle } from '../../utils/rarityDisplay'
import ItemSlotVisual from '../common/ItemSlotVisual.vue'
import ItemHoverTip from './ItemHoverTip.vue'

defineProps<{
  title: string
  emptyText: string
  items: PoolCandidate[]
  busy?: boolean
}>()

const emit = defineEmits<{
  pick: [item: PoolCandidate]
}>()

function cellStyle(item: PoolCandidate): Record<string, string> | undefined {
  if (item.rarity) {
    return rarityChipStyle(item.rarity, item.worn)
  }
  if (item.border) {
    return { borderColor: item.border }
  }
  return undefined
}
</script>

<template>
  <div class="pool-picker">
    <el-text size="small" tag="b" class="pool-picker-title">{{ title }}</el-text>
    <div v-if="!items.length" class="pool-empty">
      <el-text size="small" type="info">{{ emptyText }}</el-text>
    </div>
    <div v-else class="pool-cells">
      <el-tooltip
        v-for="item in items"
        :key="item.key"
        :effect="item.rarity ? 'light' : 'dark'"
        placement="top"
        :show-after="200"
        :popper-class="
          item.rarity
            ? 'game-hover-tip item-hover-tip item-hover-tip-light'
            : 'game-hover-tip item-hover-tip'
        "
      >
        <template #content>
          <ItemHoverTip :model="item.hover" />
        </template>
        <button
          type="button"
          class="pool-cell"
          :class="{ 'pool-worn': item.worn, 'pool-rarity': Boolean(item.rarity) }"
          :style="cellStyle(item)"
          :disabled="busy"
          @click="emit('pick', item)"
        >
          <ItemSlotVisual
            :name="item.name || item.shortName || ''"
            :icon="item.icon"
          />
        </button>
      </el-tooltip>
    </div>
  </div>
</template>

<style scoped>
.pool-picker {
  margin-top: 0.55rem;
}

.pool-picker-title {
  display: block;
  margin-bottom: 0.35rem;
  text-align: center;
}

.pool-empty {
  text-align: center;
  padding: 0.35rem 0;
}

.pool-cells {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.35rem;
}

.pool-cell {
  width: 48px;
  height: 48px;
  padding: 0.1rem;
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-regular);
}

.pool-cell:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}

.pool-worn:not(.pool-rarity) {
  border-style: solid;
  border-color: #c9930f;
  box-shadow: 0 0 0 2px #c9930f;
}

.pool-worn.pool-rarity {
  box-shadow: 0 0 0 2px #c9930f;
}

.pool-rarity {
  color: #111827;
}
</style>
