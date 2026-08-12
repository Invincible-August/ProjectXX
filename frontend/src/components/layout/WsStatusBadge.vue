<script setup lang="ts">
/**
 * WS 连接态徽标：小圆点 + tooltip；可手动重连。
 */
import { computed } from 'vue'
import { useWsStore } from '../../stores/ws'

const wsStore = useWsStore()

const color = computed(() => {
  switch (wsStore.status) {
    case 'open':
      return '#67c23a'
    case 'connecting':
    case 'reconnecting':
      return '#e6a23c'
    case 'closed':
      return '#f56c6c'
    default:
      return '#909399'
  }
})

const tip = computed(() => {
  if (!wsStore.enabled) return '强交互通道未开启（VITE_WS_ENABLED=false）'
  const base =
    {
      idle: '未连接',
      connecting: '连接中…',
      open: '已连接',
      reconnecting: '重连中…',
      closed: '已断开',
    }[wsStore.status] ?? wsStore.status
  const err = wsStore.lastError ? ` · ${wsStore.lastError}` : ''
  return `${base}${err} · 点击重连`
})

const pulse = computed(
  () => wsStore.status === 'reconnecting' || wsStore.status === 'connecting',
)

function onClick(): void {
  if (!wsStore.enabled) return
  wsStore.reconnect()
}
</script>

<template>
  <el-tooltip :content="tip" placement="bottom">
    <button
      type="button"
      class="ws-badge"
      :class="{ pulse }"
      :aria-label="tip"
      @click="onClick"
    >
      <span class="dot" :style="{ background: color }" />
      <span class="label">WS</span>
    </button>
  </el-tooltip>
</template>

<style scoped>
.ws-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 0.15rem 0.35rem;
  border-radius: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.ws-badge:hover {
  background: rgba(0, 0, 0, 0.04);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.pulse .dot {
  animation: ws-pulse 1.2s ease-in-out infinite;
}

@keyframes ws-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.45;
    transform: scale(1.25);
  }
}
</style>
