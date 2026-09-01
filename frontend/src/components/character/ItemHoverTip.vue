<script setup lang="ts">
/**
 * Shared hover card: name + corner, optional rarity badge, elements, stats, help.
 * When rarity is set, apply §0.0.3 light panel (left accent bar + RarityBadge).
 */
import { computed } from 'vue'
import type { ItemHoverModel } from '../../types/itemHover'
import { rarityPanelStyle } from '../../utils/rarityDisplay'
import RarityBadge from '../common/RarityBadge.vue'

const props = defineProps<{
  model: ItemHoverModel
}>()

const panelStyle = computed(() =>
  props.model.rarity ? rarityPanelStyle(props.model.rarity) : undefined,
)
</script>

<template>
  <div
    class="item-hover-card"
    :class="{
      'has-inspect': Boolean(model.inspect),
      'has-rarity': Boolean(model.rarity),
    }"
    :style="panelStyle"
  >
    <div class="item-hover-head">
      <div class="item-hover-title-row">
        <RarityBadge
          v-if="model.rarity"
          :rarity="model.rarity"
          :label="model.rarityLabelZh"
        />
        <span class="item-hover-name">{{ model.name }}</span>
      </div>
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
