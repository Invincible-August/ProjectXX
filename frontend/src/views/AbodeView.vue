<script setup lang="ts">
/**
 * 洞府壳：一级页；子路由挂研究室等二级房间。
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import { CAVE_LAB_PATH, CAVE_PATH } from '../constants/cave'

const route = useRoute()
const router = useRouter()

const isLab = computed(
  () => route.path === CAVE_LAB_PATH || route.path.startsWith(`${CAVE_LAB_PATH}/`),
)

function goHub(): void {
  if (route.path === CAVE_PATH) return
  void router.push(CAVE_PATH)
}

function goLab(): void {
  if (isLab.value) return
  void router.push(CAVE_LAB_PATH)
}
</script>

<template>
  <div class="abode-page">
    <AuthSessionBar />
    <div class="page-title">
      <el-button v-if="isLab" size="small" @click="goHub">← 洞府</el-button>
      <el-button v-else size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-text tag="b" size="large">{{ isLab ? '研究室' : '洞府' }}</el-text>
      <el-text type="info" size="small">{{ isLab ? '功法 / 阵盘 / 符箓图纸' : '驻地' }}</el-text>
      <div class="mode-nav">
        <el-button size="small" :type="isLab ? 'primary' : 'default'" @click="goLab">
          研究室
        </el-button>
      </div>
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
.mode-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-left: auto;
}
</style>
