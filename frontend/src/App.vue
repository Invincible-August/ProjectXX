<script setup lang="ts">
/**
 * 根壳：玩法页显示 WorldClockBar + WsStatusBadge + ChatDock；具体页面由 <RouterView /> 渲染。
 *
 * WS 为玩法壳级长连接：壳内切页只 ``connect()`` 幂等保活，不反复断连；
 * 离开玩法壳（登录/创角等）或登出才断开。
 */
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import WorldClockBar from './components/layout/WorldClockBar.vue'
import WsStatusBadge from './components/layout/WsStatusBadge.vue'
import ChatDock from './components/layout/ChatDock.vue'
import DmDialog from './components/social/DmDialog.vue'
import FerryDeathDialog from './components/reincarnation/FerryDeathDialog.vue'
import { useCharacterStore } from './stores/character'
import { useChatStore } from './stores/chat'
import { useWorldStore } from './stores/world'
import { useWsStore } from './stores/ws'

const route = useRoute()
const worldStore = useWorldStore()
const wsStore = useWsStore()
const chatStore = useChatStore()
const characterStore = useCharacterStore()

const showWorldBar = computed(() => Boolean(route.meta.showWorldBar))

// 进入玩法壳：环境轮询 + WS 长连接 + 挂机 sync；壳内路由切换不触发本 watch
watch(
  showWorldBar,
  (show) => {
    characterStore.setPlayShellActive(show)
    if (show) {
      worldStore.startPoll()
      // 已 OPEN/CONNECTING 时 connect 为空操作，保持长连接
      wsStore.connect()
      chatStore.bindPageHideClear()
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
