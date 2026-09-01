<script setup lang="ts">
/**
 * 道池图鉴网格：已收藏高亮；未获灰置。不伪造收藏。
 */
import { computed } from 'vue'
import type { DaoCatalogEntry } from '../../types/dao'
import RarityBadge from '../common/RarityBadge.vue'
import { rarityChipStyle } from '../../utils/rarityDisplay'

const props = defineProps<{
  catalog: DaoCatalogEntry[]
  /** 高亮 focus 的 dao_id */
  focusId?: string | null
}>()

const sorted = computed(() => {
  const list = [...props.catalog]
  list.sort((a, b) => Number(b.owned) - Number(a.owned) || a.label.localeCompare(b.label, 'zh'))
  return list
})
</script>

<template>
  <el-card shadow="never" class="dao-pool">
    <template #header>
      <el-text tag="b">道池图鉴</el-text>
      <el-text size="small" type="info" class="sub">
        已收藏 {{ catalog.filter((c) => c.owned).length }} / {{ catalog.length }}
      </el-text>
    </template>

    <el-empty v-if="!catalog.length" description="图鉴样本未加载" :image-size="48" />

    <div v-else class="grid">
      <div
        v-for="entry in sorted"
        :key="entry.dao_id"
        class="cell"
        :class="{
          owned: entry.owned,
          muted: !entry.owned,
          focus: focusId === entry.dao_id,
        }"
        :style="rarityChipStyle(entry.rarity || entry.rarity_label)"
      >
        <el-text tag="b" :type="entry.owned ? 'primary' : 'info'">
          {{ entry.label }}
        </el-text>
        <div class="cell-meta">
          <el-text size="small" type="info">{{ entry.category_label }}</el-text>
          <RarityBadge
            :rarity="entry.rarity || entry.rarity_label"
            :label="entry.rarity_label"
          />
        </div>
        <el-tag v-if="entry.owned" size="small" type="success">已收藏</el-tag>
        <el-tag v-else size="small" type="info">未获</el-tag>
        <el-text v-if="entry.description" size="small" class="desc">
          {{ entry.description }}
        </el-text>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.sub {
  margin-left: 0.5rem;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 0.65rem;
}

.cell {
  padding: 0.65rem;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  transition: transform 0.15s ease;
}

.cell-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
}

.cell.muted {
  opacity: 0.55;
}

.cell.focus {
  outline: 2px solid var(--el-color-primary);
  transform: scale(1.02);
}

.desc {
  margin-top: 0.2rem;
}
</style>
