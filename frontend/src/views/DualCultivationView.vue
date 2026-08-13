<script setup lang="ts">
/**
 * 双修独立页（/dual-cultivation）：复用 DualCultivationPanel。
 */
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import DualCultivationPanel from '../components/dual/DualCultivationPanel.vue'
import { useCharacterStore } from '../stores/character'
import { useGameLogStore } from '../stores/gameLog'
import { type GameLogEntry } from '../types/gameLog'

const router = useRouter()
const characterStore = useCharacterStore()
const gameLogStore = useGameLogStore()

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  gameLogStore.push(message, level)
}

onMounted(async () => {
  if (!characterStore.character) {
    const ok = await characterStore.fetchMe()
    if (!ok) {
      await router.replace('/create-character')
    }
  }
})
</script>

<template>
  <div class="dual-page">
    <AuthSessionBar />

    <div class="page-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-button size="small" @click="router.push('/social?mode=dual')">社交 · 双修</el-button>
      <el-text tag="b" size="large">双修</el-text>
      <el-text type="info" size="small">M7 L7 · 会话 / 四榜</el-text>
    </div>

    <DualCultivationPanel @log="pushLog" />
  </div>
</template>

<style scoped>
.dual-page {
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
