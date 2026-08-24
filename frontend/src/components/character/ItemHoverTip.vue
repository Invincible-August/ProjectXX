<script setup lang="ts">
/**
 * Shared hover card: name + corner, element chips, optional inspect, stats, help.
 */
import type { ItemHoverModel } from '../../types/itemHover'

defineProps<{
  model: ItemHoverModel
}>()
</script>

<template>
  <div class="item-hover-card" :class="{ 'has-inspect': Boolean(model.inspect) }">
    <div class="item-hover-head">
      <span>{{ model.name }}</span>
      <span v-if="model.cornerZh" class="item-hover-corner">{{ model.cornerZh }}</span>
    </div>
    <div v-if="model.subtitle" class="item-hover-sub">{{ model.subtitle }}</div>
    <div v-if="model.elements?.length" class="item-hover-elems">
      <span
        v-for="el in model.elements"
        :key="el.id"
        class="item-hover-chip"
        :style="el.border ? { borderColor: el.border } : undefined"
      >
        {{ el.label_zh }}
      </span>
    </div>
    <template v-if="model.inspect">
      <div class="item-hover-block-label">功效</div>
      <div class="item-hover-elems">
        <span
          v-for="tag in model.inspect.effectTags"
          :key="tag.id"
          class="item-hover-chip"
        >
          {{ tag.label_zh }}
        </span>
        <span v-if="!model.inspect.effectTags.length" class="item-hover-muted">无</span>
      </div>
      <div class="item-hover-realm">
        <span>使用条件</span>
        <span>境界 {{ model.inspect.realmReqZh }}</span>
      </div>
      <div v-if="model.helpZh" class="item-hover-section">
        <div class="item-hover-section-title">说明</div>
        <div class="item-hover-help">{{ model.helpZh }}</div>
      </div>
    </template>
    <div v-if="model.stats?.length" class="item-hover-stats">
      <div v-for="(row, idx) in model.stats" :key="`${row.label_zh}-${idx}`" class="item-hover-stat">
        <span>{{ row.label_zh }}</span>
        <span>{{ row.value }}</span>
      </div>
    </div>
    <div v-if="model.helpZh && !model.inspect" class="item-hover-help">{{ model.helpZh }}</div>
  </div>
</template>
