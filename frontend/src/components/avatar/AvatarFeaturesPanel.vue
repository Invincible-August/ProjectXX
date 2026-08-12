<script setup lang="ts">
/**
 * 化身功能看板：已解锁 / 未解锁 + 下一档预告（服务端权威文案）。
 */
import { computed } from 'vue'
import type { AvatarFeatureState, AvatarUnlockPreview } from '../../types/avatar'

const props = defineProps<{
  features: AvatarFeatureState[]
  unlockPreview?: AvatarUnlockPreview | null
  majorRealm?: string
}>()

const unlocked = computed(() => props.features.filter((f) => f.unlocked))
const locked = computed(() => props.features.filter((f) => !f.unlocked))
</script>

<template>
  <el-card shadow="never" class="features-card">
    <template #header>
      <el-text tag="b">功能解锁</el-text>
      <el-text v-if="majorRealm" size="small" type="info" class="realm-tag">
        本体 {{ majorRealm }}
      </el-text>
    </template>

    <div class="section">
      <el-text size="small" type="success">已解锁</el-text>
      <ul v-if="unlocked.length" class="feat-list">
        <li v-for="f in unlocked" :key="f.feature_id">
          <el-text size="small">{{ f.label_zh }}</el-text>
          <el-text size="small" type="info"> — {{ f.summary }}</el-text>
        </li>
      </ul>
      <el-text v-else size="small" type="info">暂无</el-text>
    </div>

    <div class="section">
      <el-text size="small" type="warning">未解锁</el-text>
      <ul v-if="locked.length" class="feat-list">
        <li v-for="f in locked" :key="f.feature_id">
          <el-text size="small">🔒 {{ f.label_zh }}</el-text>
          <el-text size="small" type="info">
            （需 {{ f.min_major }}）— {{ f.summary }}
          </el-text>
        </li>
      </ul>
      <el-text v-else size="small" type="info">已全部解锁</el-text>
    </div>

    <el-alert
      v-if="unlockPreview"
      type="info"
      :closable="false"
      show-icon
      class="preview"
    >
      <template #title>
        下一档 {{ unlockPreview.next_major }} 将开放：
        {{ unlockPreview.features.map((x) => x.label_zh).join('、') }}
      </template>
    </el-alert>
  </el-card>
</template>

<style scoped>
.features-card :deep(.el-card__header) {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}

.realm-tag {
  margin-left: 0.25rem;
}

.section {
  margin-bottom: 0.75rem;
}

.feat-list {
  margin: 0.25rem 0 0;
  padding-left: 1.1rem;
}

.preview {
  margin-top: 0.5rem;
}
</style>
