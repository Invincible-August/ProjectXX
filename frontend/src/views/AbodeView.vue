<script setup lang="ts">
/**
 * 洞府壳：一级页；子路由挂工坊 / 研究室等二级房间。
 * 房间入口只在枢纽大卡，标题行不再放小切换钮。
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import { CAVE_LAB_PATH, CAVE_PATH, CAVE_WORKSHOP_PATH } from '../constants/cave'

const route = useRoute()
const router = useRouter()

const currentRoom = computed<'hub' | 'workshop' | 'lab'>(() => {
  if (route.path === CAVE_WORKSHOP_PATH || route.path.startsWith(`${CAVE_WORKSHOP_PATH}/`)) {
    return 'workshop'
  }
  if (route.path === CAVE_LAB_PATH || route.path.startsWith(`${CAVE_LAB_PATH}/`)) {
    return 'lab'
  }
  return 'hub'
})

const titleZh = computed(() => {
  if (currentRoom.value === 'workshop') return '工坊'
  if (currentRoom.value === 'lab') return '研究室'
  return '洞府'
})

const subtitleZh = computed(() => {
  if (currentRoom.value === 'workshop') return '炼丹 / 炼器 / 符箓 / 傀儡'
  if (currentRoom.value === 'lab') return '功法 / 阵盘 / 符箓图纸'
  return '驻地'
})

function goHub(): void {
  if (route.path === CAVE_PATH) return
  void router.push(CAVE_PATH)
}
</script>

<template>
  <div class="abode-page">
    <AuthSessionBar />
    <div class="page-title">
      <el-button v-if="currentRoom !== 'hub'" size="small" @click="goHub">← 洞府</el-button>
      <el-button v-else size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-text tag="b" size="large">{{ titleZh }}</el-text>
      <el-text type="info" size="small">{{ subtitleZh }}</el-text>
    </div>
    <router-view />
  </div>
</template>

<style scoped>
.abode-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 1rem 1rem 2rem;
}
.page-title {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.5rem 0.75rem;
  margin: 0.75rem 0 1rem;
}
</style>
