<script setup lang="ts">
/**
 * 本会话战报列表：数据来自 sessionStorage（登出 / 关闭浏览器后清除）。
 *
 * 战报零保留是服务端设计约定，UI 必须明示留存策略。
 */
import { useBattleStore } from '../../stores/battle'

const battleStore = useBattleStore()

const emit = defineEmits<{
  open: [sessionKey: string]
}>()
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">本会话战报（{{ battleStore.sessionReports.length }}）</el-text>
    </template>

    <el-alert
      title="战报仅本次登录有效，退出或关闭浏览器后将清除"
      type="info"
      show-icon
      :closable="false"
      class="report-notice"
    />

    <el-empty
      v-if="battleStore.sessionReports.length === 0"
      description="尚无战报，去开一战吧"
      :image-size="60"
    />
    <ul v-else class="report-list">
      <li
        v-for="entry in battleStore.sessionReports"
        :key="entry.session_key"
        class="report-item"
        :class="{ active: entry.session_key === battleStore.activeReportKey }"
      >
        <el-tag :type="entry.result === 'win' ? 'success' : 'danger'" size="small">
          {{ entry.result === 'win' ? '胜' : '负' }}
        </el-tag>
        <el-text size="small" class="report-title">{{ entry.title }}</el-text>
        <el-text type="info" size="small">
          {{ new Date(entry.created_at).toLocaleTimeString() }}
        </el-text>
        <el-button size="small" text type="primary" @click="emit('open', entry.session_key)">
          播放
        </el-button>
      </li>
    </ul>
  </el-card>
</template>

<style scoped>
.report-notice {
  margin-bottom: 0.75rem;
}

.report-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  max-height: 320px;
  overflow-y: auto;
}

.report-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.4rem;
  border-radius: 4px;
}

.report-item.active {
  background: var(--el-color-primary-light-9);
}

.report-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
