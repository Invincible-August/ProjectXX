<script setup lang="ts">
/**
 * 轮回预览：保留 / 失去清单（只读）。
 */
import type { ReincarnationPreview } from '../../types/reincarnation'

defineProps<{
  preview: ReincarnationPreview | null
  loading?: boolean
}>()
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">轮回预览</el-text>
    </template>

    <el-skeleton v-if="loading && !preview" animated :rows="3" />
    <el-empty v-else-if="!preview" description="请先拉取预览" :image-size="48" />
    <template v-else>
      <el-text size="small" type="info" class="path">
        路径：{{ preview.path }} · 主动预计 +{{ preview.points_gain }} 点
        <template v-if="preview.points_gain_forced != null">
          （死亡仅 +{{ preview.points_gain_forced }}）
        </template>
      </el-text>
      <el-text v-if="preview.peak_major" size="small" type="info" class="path">
        峰值境界：{{ preview.peak_major }}
        <template v-if="preview.permanent_delta">
          · 永久加成 Δ初{{ ((preview.permanent_delta.initial_attr || 0) * 100).toFixed(1) }}%
          / 小{{ ((preview.permanent_delta.minor_growth || 0) * 100).toFixed(1) }}%
          / 大{{ ((preview.permanent_delta.major_growth || 0) * 100).toFixed(1) }}%
          / 率+{{ ((preview.permanent_delta.break_rate || 0) * 100).toFixed(1) }}%
        </template>
      </el-text>
      <el-text
        v-if="preview.reincarnation_bag_slots_after != null"
        size="small"
        type="info"
        class="path"
      >
        结算后轮回袋容量：{{ preview.reincarnation_bag_slots_after }}
      </el-text>
      <el-descriptions :column="1" size="small" border class="desc">
        <el-descriptions-item label="保留">
          <el-tag
            v-for="item in preview.keep"
            :key="item"
            size="small"
            type="success"
            class="tag"
          >
            {{ item }}
          </el-tag>
          <el-text v-if="!preview.keep.length" size="small">—</el-text>
        </el-descriptions-item>
        <el-descriptions-item label="失去">
          <el-tag
            v-for="item in preview.lose"
            :key="item"
            size="small"
            type="danger"
            class="tag"
          >
            {{ item }}
          </el-tag>
          <el-text v-if="!preview.lose.length" size="small">—</el-text>
        </el-descriptions-item>
      </el-descriptions>
      <el-text v-if="preview.pet_carry_note" size="small" type="warning" class="pet">
        {{ preview.pet_carry_note }}
      </el-text>
    </template>
  </el-card>
</template>

<style scoped>
.path {
  display: block;
  margin-bottom: 0.5rem;
}

.desc {
  margin-top: 0.25rem;
}

.tag {
  margin: 0 0.25rem 0.25rem 0;
}

.pet {
  display: block;
  margin-top: 0.5rem;
}
</style>
