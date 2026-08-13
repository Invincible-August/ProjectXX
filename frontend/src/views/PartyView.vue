<script setup lang="ts">
/**
 * 独立队伍页（/party）：建队、邀请、踢人、队友情报。
 */
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import PartyPanel from '../components/party/PartyPanel.vue'
import { useCharacterStore } from '../stores/character'
import { useChatStore } from '../stores/chat'
import { useGameLogStore } from '../stores/gameLog'
import { type GameLogEntry } from '../types/gameLog'

const router = useRouter()
const characterStore = useCharacterStore()
const chatStore = useChatStore()
const gameLogStore = useGameLogStore()

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  gameLogStore.push(message, level)
}

onMounted(async () => {
  if (!characterStore.character) {
    const ok = await characterStore.fetchMe()
    if (!ok) {
      await router.replace('/create-character')
      return
    }
  }
  await chatStore.refreshPartyMe()
  pushLog('队伍页已就绪：建队 / 邀请 / 踢人 / 查看队友摘要。', 'info')
})
</script>

<template>
  <div class="party-page">
    <AuthSessionBar />

    <div class="page-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-text tag="b" size="large">队伍</el-text>
      <el-text type="info" size="small">队长邀请 · 踢人 · 队友情报</el-text>
      <el-button size="small" @click="router.push('/social?mode=friends')">道友</el-button>
      <el-button size="small" @click="router.push('/social?mode=party')">社交 · 队伍</el-button>
    </div>

    <div class="main-grid">
      <div class="main-left">
        <PartyPanel @log="pushLog" />
      </div>
      <aside class="main-side">
        <el-card shadow="never">
          <template #header>
            <el-text tag="b" size="small">规则</el-text>
          </template>
          <ul class="rules">
            <li>同一角色同时只能加入一支队伍或团队。</li>
            <li>队伍最多 5 人；超过请队长「转换为团队」（最多 40 人）；人数≤5 时可「转回队伍」。</li>
            <li>仅队长/团长可邀请与踢人；邀请须双方在线且为道友/同门/师徒。</li>
            <li>邀请 1 分钟内未接受视为拒绝；列表显示倒计时与绿接受 / 红拒绝。</li>
            <li>团队仅可挑战团队秘境、团队/野外 Boss、势力争夺；不可进普通秘境；非团队 Boss 无掉落与修为。</li>
            <li>队伍聊天请在聊天坞「队伍」页签发言（不可发机缘）。</li>
          </ul>
        </el-card>
        <el-card v-if="gameLogStore.entries.length" shadow="never">
          <template #header>
            <el-text tag="b" size="small">事件日志（同步大厅）</el-text>
          </template>
          <div v-for="e in gameLogStore.entries.slice(-8)" :key="e.id" class="log-line">
            <el-text size="small">{{ e.message }}</el-text>
          </div>
        </el-card>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.party-page {
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

.main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 1rem;
}

@media (max-width: 860px) {
  .main-grid {
    grid-template-columns: 1fr;
  }
}

.main-side {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.rules {
  margin: 0;
  padding-left: 1.1rem;
  font-size: 0.85rem;
  line-height: 1.55;
}

.rules li + li {
  margin-top: 0.35rem;
}

.log-line {
  margin-bottom: 0.25rem;
}
</style>
