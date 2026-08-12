<script setup lang="ts">
/**
 * 根壳：玩法页显示 WorldClockBar + WsStatusBadge + ChatDock；具体页面由 <RouterView /> 渲染。
 */
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import WorldClockBar from './components/layout/WorldClockBar.vue'
import WsStatusBadge from './components/layout/WsStatusBadge.vue'
import ChatDock from './components/layout/ChatDock.vue'
import DmDialog from './components/social/DmDialog.vue'
import FerryDeathDialog from './components/reincarnation/FerryDeathDialog.vue'
import { useChatStore } from './stores/chat'
import { useWorldStore } from './stores/world'
import { useWsStore } from './stores/ws'

const route = useRoute()
const worldStore = useWorldStore()
const wsStore = useWsStore()
const chatStore = useChatStore()

const showWorldBar = computed(() => Boolean(route.meta.showWorldBar))

// 进入玩法壳时开环境轮询 + WS；离开时停（避免登录页空转）
watch(
  showWorldBar,
  (show) => {
    if (show) {
      worldStore.startPoll()
      wsStore.connect()
      // 关浏览器 / 关标签时清空本会话聊天与已结束机缘本地态
      chatStore.bindPageHideClear()
      // 进玩法壳即开始收齐各频道消息（不依赖聊天坞打开）
      void chatStore.startSessionListening()
    } else {
      worldStore.stopPoll()
      wsStore.disconnect()
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="app-shell">
    <div v-if="showWorldBar" class="play-chrome">
      <WorldClockBar class="play-chrome-clock" />
      <WsStatusBadge class="play-chrome-ws" />
    </div>
    <RouterView />
    <ChatDock v-if="showWorldBar" />
    <DmDialog v-if="showWorldBar" />
    <FerryDeathDialog />
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
}

.play-chrome {
  display: flex;
  align-items: stretch;
  gap: 0;
}

.play-chrome-clock {
  flex: 1;
  min-width: 0;
}

.play-chrome-ws {
  flex-shrink: 0;
  align-self: center;
  margin-right: 0.75rem;
}
</style>
