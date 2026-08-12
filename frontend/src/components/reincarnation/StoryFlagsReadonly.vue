<script setup lang="ts">
/**
 * 前世阅历（story flags）只读；无剧情播放器。
 */
import { computed } from 'vue'
import { useCharacterStore } from '../../stores/character'
import type { ReincarnationLogItem } from '../../types/reincarnation'

const props = defineProps<{
  logs?: ReincarnationLogItem[]
}>()

const characterStore = useCharacterStore()

const nodes = computed(
  () => characterStore.character?.story_flags?.experienced_nodes ?? [],
)
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">前世阅历（系统标记）</el-text>
    </template>

    <el-text size="small" type="info" class="tip">
      剧情播放器将在后续开放。此处仅展示已历节点 ID。
    </el-text>

    <div v-if="nodes.length" class="nodes">
      <el-tag v-for="id in nodes" :key="id" size="small" type="info" class="node">
        {{ id }}
      </el-tag>
    </div>
    <el-empty v-else description="尚无已历节点" :image-size="40" />

    <el-divider content-position="left">轮回流水</el-divider>
    <el-timeline v-if="logs?.length">
      <el-timeline-item
        v-for="item in logs"
        :key="item.id"
        :timestamp="item.created_at"
        placement="top"
      >
        {{ item.summary || item.path }}
        <template v-if="item.from_realm_display">
          · {{ item.from_realm_display }} → {{ item.to_realm_display || '?' }}
        </template>
        <el-text
          v-if="item.points_gain != null || item.points_gained != null"
          size="small"
          type="success"
          class="pts"
        >
          +{{ item.points_gain ?? item.points_gained }} 轮回点
        </el-text>
      </el-timeline-item>
    </el-timeline>
    <el-empty v-else description="尚无轮回流水" :image-size="40" />
  </el-card>
</template>

<style scoped>
.tip {
  display: block;
  margin-bottom: 0.75rem;
}

.nodes {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.node {
  font-family: ui-monospace, monospace;
}

.pts {
  display: block;
  margin-top: 0.25rem;
}
</style>
