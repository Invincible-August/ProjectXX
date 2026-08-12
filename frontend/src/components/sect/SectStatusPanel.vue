<script setup lang="ts">
/**
 * 宗门状态面板：入宗 / 散修提示 / 贡献 / 已解锁功能。
 */
import { computed } from 'vue'
import type { SectSummary } from '../../types/sect'

const props = defineProps<{
  sect: SectSummary | null
}>()

const featureText = computed(() => {
  const list = props.sect?.unlocked_features_zh ?? []
  return list.length ? list.join('、') : '暂无'
})
</script>

<template>
  <el-card shadow="never" class="sect-status">
    <template #header>
      <el-text tag="b">宗门状态</el-text>
    </template>

    <el-empty v-if="!sect" description="暂无宗门数据" :image-size="48" />

    <div v-else class="status-grid">
      <template v-if="sect.in_sect">
        <div class="row">
          <el-text type="info" size="small">宗门</el-text>
          <el-text tag="b">{{ sect.name || '—' }}</el-text>
          <el-tag size="small" type="success">
            {{ sect.rank_label_zh || sect.role_label_zh || sect.role || '弟子' }}
          </el-tag>
          <el-tag v-if="sect.kind" size="small" type="info">
            {{ sect.kind === 'npc' ? 'NPC 宗' : '自建宗' }}
          </el-tag>
          <el-tag v-if="sect.grade" size="small">{{ sect.grade }}</el-tag>
        </div>
        <div v-if="sect.motto" class="row">
          <el-text type="info" size="small">箴言</el-text>
          <el-text>{{ sect.motto }}</el-text>
        </div>
        <div v-if="sect.specialty" class="row">
          <el-text type="info" size="small">专精</el-text>
          <el-text>{{ sect.specialty }}</el-text>
        </div>
        <div class="row">
          <el-text type="info" size="small">贡献</el-text>
          <el-text tag="b">{{ sect.contrib }}</el-text>
          <el-text type="info" size="small">挂机占位</el-text>
          <el-text>×{{ Number(sect.idle_bonus_vs_wanderer).toFixed(2) }}</el-text>
        </div>
        <div class="row">
          <el-text type="info" size="small">已开功能</el-text>
          <el-text>{{ featureText }}</el-text>
        </div>
      </template>

      <template v-else>
        <div class="row">
          <el-tag size="small" type="warning">散修</el-tag>
          <el-text>尚未入宗，可通关；入宗后挂机修为占位提升。</el-text>
        </div>
        <div class="row">
          <el-text type="info" size="small">贡献</el-text>
          <el-text>{{ sect.contrib }}</el-text>
        </div>
      </template>

      <el-alert
        v-if="sect.hint_zh"
        :title="sect.hint_zh"
        type="info"
        :closable="false"
        show-icon
      />
    </div>
  </el-card>
</template>

<style scoped>
.status-grid {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}
</style>
