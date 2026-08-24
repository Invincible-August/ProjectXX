<script setup lang="ts">
/**
 * Compact wrap grid for learned/collection pickers (not one full-width row per item).
 */
import type { PoolCandidate } from '../../types/itemHover'
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
        effect="dark"
        placement="top"
        :show-after="200"
        popper-class="game-hover-tip item-hover-tip"
      >
        <template #content>
          <ItemHoverTip :model="item.hover" />
        </template>
        <button
          type="button"
          class="pool-cell"
          :class="{ 'pool-worn': item.worn }"
          :style="item.border ? { borderColor: item.border } : undefined"
          :disabled="busy"
          @click="emit('pick', item)"
        >
          <span class="pool-caption">{{ item.shortName }}</span>
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
}

.pool-cell:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}

.pool-worn {
  border-style: solid;
  border-color: #c9930f;
  box-shadow: 0 0 0 2px #c9930f;
}

.pool-caption {
  font-size: 12px;
  line-height: 1.15;
  text-align: center;
  color: var(--el-text-color-regular);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
</style>
