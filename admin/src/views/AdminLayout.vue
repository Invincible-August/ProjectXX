<template>
  <div class="layout">
    <aside class="side">
      <div class="side-brand">
        <strong>Project修仙</strong>
        <span>GM 运营台</span>
      </div>

      <div class="side-nav">
        <el-menu :default-active="active" :default-openeds="['player']" router>
          <el-sub-menu index="player">
            <template #title>玩家管理</template>
            <el-menu-item index="/players/accounts">账号管理</el-menu-item>
            <el-menu-item index="/players/characters">角色管理</el-menu-item>
          </el-sub-menu>
        </el-menu>
      </div>

      <div class="side-foot">
        <div>{{ auth.user?.display_name }}</div>
        <div class="roles">{{ auth.user?.roles?.join(', ') }}</div>
        <el-button size="small" @click="onLogout">退出</el-button>
      </div>
    </aside>
    <main class="main">
      <div class="main-scroll">
        <router-view />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
/**
 * 运营台布局（整改首版）：侧栏以玩家管理为入口，旧配置域菜单暂下线。
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAdminAuthStore } from '../stores/auth'

const auth = useAdminAuthStore()
const route = useRoute()
const router = useRouter()

const active = computed(() => route.path)

function onLogout() {
  auth.logout()
  void router.push({ name: 'login' })
}
</script>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 240px 1fr;
  height: 100vh;
  overflow: hidden;
}
.side {
  background: #16352f;
  color: #edf7f4;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100vh;
  overflow: hidden;
}
.side-brand {
  flex: 0 0 auto;
  padding: 16px 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.side-brand span {
  opacity: 0.7;
  font-size: 12px;
}
.side-nav {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding-bottom: 8px;
}
.side-nav::-webkit-scrollbar {
  width: 6px;
}
.side-nav::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.25);
  border-radius: 3px;
}
:deep(.el-menu) {
  border-right: none;
  background: transparent;
}
:deep(.el-menu-item),
:deep(.el-sub-menu__title) {
  color: #d7ebe6;
}
:deep(.el-menu-item.is-active) {
  background: rgba(255, 255, 255, 0.1) !important;
  color: #fff;
}
:deep(.el-sub-menu .el-menu) {
  background: rgba(0, 0, 0, 0.12);
}
.side-foot {
  flex: 0 0 auto;
  padding: 12px 16px 16px;
  font-size: 12px;
  opacity: 0.9;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}
.roles {
  margin: 4px 0 10px;
  opacity: 0.7;
  word-break: break-all;
}
.main {
  min-height: 0;
  height: 100vh;
  overflow: hidden;
  background: #eef3f1;
}
.main-scroll {
  height: 100%;
  overflow: hidden;
  padding: 20px 24px 16px;
  display: flex;
  flex-direction: column;
}
@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
    height: auto;
    overflow: visible;
  }
  .side {
    height: auto;
    max-height: 42vh;
  }
  .main {
    height: auto;
    overflow: visible;
  }
  .main-scroll {
    height: auto;
    overflow: visible;
  }
}
</style>
