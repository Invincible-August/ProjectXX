<script setup lang="ts">
/**
 * 社交中心（/social）：道友 / 队伍 / 双修 / 交易 / 邮件 / 师徒 / 引渡。
 */
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import DualCultivationPanel from '../components/dual/DualCultivationPanel.vue'
import FaceTradePanel from '../components/market/FaceTradePanel.vue'
import PartyPanel from '../components/party/PartyPanel.vue'
import FriendListPanel from '../components/social/FriendListPanel.vue'
import FerryRescuePanel from '../components/social/FerryRescuePanel.vue'
import MailBoxPanel from '../components/social/MailBoxPanel.vue'
import MentorPanel from '../components/social/MentorPanel.vue'
import { useCharacterStore } from '../stores/character'
import { useGameLogStore } from '../stores/gameLog'
import { type GameLogEntry } from '../types/gameLog'

/** 合法 mode（gift 已并入 mail，访问时重定向） */
type SocialMode =
  | 'friends'
  | 'party'
  | 'dual'
  | 'trade'
  | 'mail'
  | 'mentor'
  | 'ferry'

const MODE_SET = new Set<string>([
  'friends',
  'party',
  'dual',
  'trade',
  'mail',
  'mentor',
  'ferry',
])

const route = useRoute()
const router = useRouter()
const characterStore = useCharacterStore()
const gameLogStore = useGameLogStore()

const mode = computed<SocialMode>(() => {
  const m = route.query.mode
  if (typeof m === 'string' && MODE_SET.has(m)) {
    return m as SocialMode
  }
  return 'friends'
})

const mailUnread = computed(
  () => Number(characterStore.character?.social_badges?.mail_unread ?? 0),
)

const tradePeer = computed(() => {
  const p = route.query.peer
  return typeof p === 'string' ? p : null
})

const tradeSessionId = computed(() => {
  const s = route.query.session
  if (typeof s === 'string' && /^\d+$/.test(s)) {
    return Number(s)
  }
  return null
})

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  gameLogStore.push(message, level)
}

function setMode(next: SocialMode): void {
  const query: Record<string, string> = {
    ...(route.query as Record<string, string>),
    mode: next,
  }
  if (next !== 'trade') {
    delete query.peer
    delete query.session
  }
  void router.replace({ query })
}

function onTradeSessionChange(sessionId: number | null): void {
  const query: Record<string, string> = {
    ...(route.query as Record<string, string>),
    mode: 'trade',
  }
  if (sessionId && sessionId > 0) {
    query.session = String(sessionId)
  } else {
    delete query.session
  }
  void router.replace({ query })
}

watch(
  () => route.query.mode,
  (m) => {
    if (m === 'gift') {
      void router.replace({ query: { ...route.query, mode: 'mail' } })
    }
  },
  { immediate: true },
)

onMounted(async () => {
  if (!characterStore.character) {
    const ok = await characterStore.fetchMe()
    if (!ok) {
      await router.replace('/create-character')
      return
    }
  }
  pushLog('社交中心已就绪：道友 / 队伍 / 双修 / 交易 / 邮件。', 'info')
  const rawMode = String(route.query.mode ?? '')
  if (rawMode === 'gift') {
    void router.replace({ query: { ...route.query, mode: 'mail' } })
    return
  }
  if (!MODE_SET.has(rawMode)) {
    void router.replace({ query: { ...route.query, mode: 'friends' } })
  }
})
</script>

<template>
  <div class="social-page">
    <AuthSessionBar />

    <div class="page-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-text tag="b" size="large">社交</el-text>
      <el-text type="info" size="small">道友 · 队伍 · 双修 · 交易 · 邮件</el-text>
      <div class="mode-nav">
        <el-button
          size="small"
          :type="mode === 'friends' ? 'primary' : 'default'"
          @click="setMode('friends')"
        >
          道友
        </el-button>
        <el-button
          size="small"
          :type="mode === 'party' ? 'primary' : 'default'"
          @click="setMode('party')"
        >
          队伍
        </el-button>
        <el-button
          size="small"
          :type="mode === 'dual' ? 'primary' : 'default'"
          @click="setMode('dual')"
        >
          双修
        </el-button>
        <el-button
          size="small"
          :type="mode === 'trade' ? 'primary' : 'default'"
          @click="setMode('trade')"
        >
          交易
        </el-button>
        <el-button
          size="small"
          :type="mode === 'mail' ? 'primary' : 'default'"
          @click="setMode('mail')"
        >
          邮件
          <span v-if="mailUnread > 0" class="badge">{{ mailUnread }}</span>
        </el-button>
        <el-button
          size="small"
          :type="mode === 'mentor' ? 'primary' : 'default'"
          @click="setMode('mentor')"
        >
          师徒
        </el-button>
        <el-button
          size="small"
          :type="mode === 'ferry' ? 'primary' : 'default'"
          @click="setMode('ferry')"
        >
          引渡
        </el-button>
      </div>
    </div>

    <div class="main-grid">
      <div class="main-left">
        <FriendListPanel v-if="mode === 'friends'" @log="pushLog" />
        <PartyPanel v-else-if="mode === 'party'" @log="pushLog" />
        <DualCultivationPanel v-else-if="mode === 'dual'" @log="pushLog" />
        <FaceTradePanel
          v-else-if="mode === 'trade'"
          :peer="tradePeer"
          :session-id="tradeSessionId"
          @log="pushLog"
          @session-change="onTradeSessionChange"
        />
        <MailBoxPanel v-else-if="mode === 'mail'" @log="pushLog" />
        <MentorPanel v-else-if="mode === 'mentor'" @log="pushLog" />
        <FerryRescuePanel v-else-if="mode === 'ferry'" @log="pushLog" />
      </div>
      <aside class="main-side">
        <el-card shadow="never">
          <template #header>
            <el-text tag="b" size="small">道友数</el-text>
          </template>
          <el-text>
            {{ characterStore.character?.friend_count ?? 0 }}
          </el-text>
        </el-card>
        <el-card shadow="never">
          <template #header>
            <el-text tag="b" size="small">未读邮件</el-text>
          </template>
          <el-text>{{ mailUnread }}</el-text>
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
.social-page {
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
  width: 100%;
}

.badge {
  margin-left: 0.25rem;
  font-size: 0.75rem;
  color: var(--el-color-danger);
}

.main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 200px;
  gap: 1rem;
  align-items: start;
}

.main-left {
  min-width: 0;
}

.main-side {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.log-line {
  margin-bottom: 0.25rem;
}

@media (max-width: 800px) {
  .main-grid {
    grid-template-columns: 1fr;
  }
}
</style>
