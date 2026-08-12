<script setup lang="ts">
/**
 * 大厅事件日志：文字贴底、新条目往上顶；本会话全量保留，窗内滚动。
 */
import { nextTick, ref, watch } from 'vue'
import type { GameLogEntry } from '../types/gameLog'

const props = defineProps<{
  /** 日志条目（新条目追加在末尾；不截断） */
  entries: GameLogEntry[]
}>()

const bodyRef = ref<HTMLElement | null>(null)

/**
 * 滚到最底部（最新日志贴在可视区下方）。
 */
async function scrollToBottom(): Promise<void> {
  await nextTick()
  const el = bodyRef.value
  if (el) {
    el.scrollTop = el.scrollHeight
  }
}

watch(
  () => props.entries.length,
  () => {
    void scrollToBottom()
  },
  { flush: 'post' },
)

/** 级别 → Element Plus 文本类型 */
function textType(level: GameLogEntry['level']): '' | 'success' | 'warning' | 'info' {
  if (level === 'success') return 'success'
  if (level === 'warning') return 'warning'
  if (level === 'system') return 'info'
  return ''
}
</script>

<template>
  <el-card shadow="never" class="log-panel">
    <template #header>
      <div class="log-header">
        <el-text tag="b">事件日志</el-text>
        <el-text type="info" size="small">
          本会话 {{ entries.length }} 条 · 最新在下 · 上翻看更早
        </el-text>
      </div>
    </template>

    <div ref="bodyRef" class="log-body">
      <!-- margin-top:auto：内容不足一屏时整块贴底；超出后从底部往上堆 -->
      <div class="log-body-inner">
        <el-empty
          v-if="entries.length === 0"
          description="暂无事件"
          :image-size="48"
        />
        <div
          v-for="entry in entries"
          :key="entry.id"
          class="log-line"
        >
          <el-text type="info" size="small" class="log-time">[{{ entry.time }}]</el-text>
          <el-text :type="textType(entry.level)" size="small" class="log-msg">
            {{ entry.message }}
          </el-text>
        </div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.log-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.log-panel :deep(.el-card__header) {
  flex-shrink: 0;
  padding: 0.75rem 1rem;
}

.log-panel :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0.5rem 1rem 0.75rem;
  overflow: hidden;
}

.log-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.log-body {
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  font-family: ui-monospace, 'Cascadia Code', 'Consolas', monospace;
  line-height: 1.55;
  padding: 0.25rem 0.15rem 0.25rem 0;
  overscroll-behavior: contain;
}

.log-body-inner {
  margin-top: auto;
  width: 100%;
  display: flex;
  flex-direction: column;
}

.log-line {
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
  padding: 0.15rem 0;
}

.log-time {
  flex-shrink: 0;
  opacity: 0.75;
}

.log-msg {
  word-break: break-word;
}
</style>
