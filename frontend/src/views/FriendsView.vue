<script setup lang="ts">
/**
 * 独立道友页（/friends）：列表 + 私聊/组队/邀请化身/面交入口。
 * 化身助战开关在「化身」页；邀请开启则立即入队。
 */
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import FriendListPanel from '../components/social/FriendListPanel.vue'
import { useCharacterStore } from '../stores/character'
import { useFriendsStore } from '../stores/friends'
import { useGameLogStore } from '../stores/gameLog'
import { type GameLogEntry } from '../types/gameLog'

const router = useRouter()
const characterStore = useCharacterStore()
const friendsStore = useFriendsStore()
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
  await friendsStore.refresh()
  pushLog('道友页已就绪：私聊 / 邀请化身 / 交易；组队请到队伍页。化身助战开关见化身页。', 'info')
})
</script>

<template>
  <div class="friends-page">
    <AuthSessionBar />

    <div class="page-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-text tag="b" size="large">道友</el-text>
      <el-text type="info" size="small">修为 · 在线 · 社交动作</el-text>
      <el-button size="small" @click="router.push('/party')">队伍</el-button>
      <el-button size="small" @click="router.push('/avatar')">化身助战开关</el-button>
      <el-button size="small" @click="router.push('/social')">社交中心</el-button>
      <el-button size="small" @click="router.push('/social?mode=trade')">交易台</el-button>
    </div>

    <div class="main-grid">
      <div class="main-left">
        <FriendListPanel show-actions @log="pushLog" />
      </div>
      <aside class="main-side">
        <el-card shadow="never">
          <template #header>
            <el-text tag="b" size="small">道友数</el-text>
          </template>
          <el-text>
            {{ friendsStore.friendCount }} / {{ friendsStore.maxFriends || '—' }}
          </el-text>
          <el-text size="small" type="info" class="side-hint">
            「邀请化身」需对方在化身页开启助战；关闭时提示闭关，忙碌时提示助战中。
          </el-text>
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
.friends-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 0.75rem 1rem 2rem;
}

.page-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
  margin-bottom: 0.75rem;
}

.main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 260px;
  gap: 0.75rem;
}

@media (max-width: 860px) {
  .main-grid {
    grid-template-columns: 1fr;
  }
}

.side-hint {
  display: block;
  margin-top: 0.5rem;
  line-height: 1.45;
}

.log-line {
  margin-bottom: 0.25rem;
}
</style>
