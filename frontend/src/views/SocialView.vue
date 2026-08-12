<script setup lang="ts">
/**
 * 社交页（M7 L6 · /social）：道友 / 邮件 / 赠送 / 师徒 / 引渡救援。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import FriendListPanel from '../components/social/FriendListPanel.vue'
import FerryRescuePanel from '../components/social/FerryRescuePanel.vue'
import GiftPanel from '../components/social/GiftPanel.vue'
import MailBoxPanel from '../components/social/MailBoxPanel.vue'
import MentorPanel from '../components/social/MentorPanel.vue'
import { useCharacterStore } from '../stores/character'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'

/** 合法 mode */
type SocialMode = 'friends' | 'mail' | 'gift' | 'mentor' | 'ferry'

const MODE_SET = new Set<string>(['friends', 'mail', 'gift', 'mentor', 'ferry'])

const route = useRoute()
const router = useRouter()
const characterStore = useCharacterStore()

const logEntries = ref<GameLogEntry[]>([])

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

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logEntries.value = [...logEntries.value.slice(-49), createLogEntry(message, level)]
}

function setMode(next: SocialMode): void {
  void router.replace({ query: { ...route.query, mode: next } })
}

onMounted(async () => {
  if (!characterStore.character) {
    const ok = await characterStore.fetchMe()
    if (!ok) {
      await router.replace('/create-character')
      return
    }
  }
  pushLog('社交页已就绪：道友 / 邮件 / 赠送 / 师徒 / 引渡。', 'info')
  if (!MODE_SET.has(String(route.query.mode ?? ''))) {
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
      <el-text type="info" size="small">M7 L6 · 师徒 / 引渡</el-text>
      <div class="mode-nav">
        <el-button
          size="small"
          :type="mode === 'friends' ? 'primary' : 'default'"
          @click="router.push('/friends')"
        >
          道友（独立页）
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
          :type="mode === 'gift' ? 'primary' : 'default'"
          @click="setMode('gift')"
        >
          赠送
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
        <MailBoxPanel v-else-if="mode === 'mail'" @log="pushLog" />
        <GiftPanel v-else-if="mode === 'gift'" @log="pushLog" />
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
        <el-card v-if="logEntries.length" shadow="never">
          <template #header>
            <el-text tag="b" size="small">本页日志</el-text>
          </template>
          <div v-for="e in logEntries.slice(-8)" :key="e.id" class="log-line">
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
  grid-template-columns: minmax(0, 1fr) 220px;
  gap: 1rem;
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
