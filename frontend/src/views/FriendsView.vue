<script setup lang="ts">
/**
 * 独立道友页（/friends）：列表 + 私聊/赠礼/组队/助战/面交入口。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import FriendListPanel from '../components/social/FriendListPanel.vue'
import { useCharacterStore } from '../stores/character'
import { useFriendsStore } from '../stores/friends'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'
import {
  acceptAvatarAssist,
  fetchAvatarAssistMe,
  rejectAvatarAssist,
  setAvatarAssistSettings,
  type AvatarAssistSessionPublic,
} from '../api/avatar'
import { ElMessage } from 'element-plus'
import { useAvatarStore } from '../stores/avatar'

const router = useRouter()
const characterStore = useCharacterStore()
const friendsStore = useFriendsStore()
const avatarStore = useAvatarStore()

const logEntries = ref<GameLogEntry[]>([])
const assistIncoming = ref<AvatarAssistSessionPublic[]>([])
const assistBusy = ref(false)
const assistEnabled = ref(false)

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logEntries.value = [...logEntries.value.slice(-49), createLogEntry(message, level)]
}

async function refreshAssist(): Promise<void> {
  const envelope = await fetchAvatarAssistMe()
  if (envelope.code !== 0 || !envelope.data) return
  const data = envelope.data as {
    as_owner?: AvatarAssistSessionPublic[]
    as_borrower?: AvatarAssistSessionPublic[]
    incoming?: AvatarAssistSessionPublic[]
    assist_friends_enabled?: boolean
  }
  if (typeof data.assist_friends_enabled === 'boolean') {
    assistEnabled.value = data.assist_friends_enabled
  }
  // 主人视角：待我确认的 invited
  assistIncoming.value = (data.as_owner ?? data.incoming ?? []).filter(
    (x) => x.status === 'invited',
  )
}

async function onToggleAssist(val: boolean): Promise<void> {
  assistBusy.value = true
  try {
    const envelope = await setAvatarAssistSettings(val)
    if (envelope.code !== 0) {
      ElMessage.error(envelope.message || '开关失败')
      assistEnabled.value = !val
      return
    }
    assistEnabled.value = Boolean(envelope.data?.enabled ?? val)
    ElMessage.success(envelope.data?.message || (val ? '已允许道友助战' : '已关闭助战'))
    pushLog(envelope.data?.message || '助战开关已更新', 'success')
    await avatarStore.load()
  } finally {
    assistBusy.value = false
  }
}

async function onAcceptAssist(session: AvatarAssistSessionPublic): Promise<void> {
  assistBusy.value = true
  try {
    const envelope = await acceptAvatarAssist(session.id)
    if (envelope.code !== 0) {
      ElMessage.error(envelope.message || '接受失败')
      return
    }
    ElMessage.success(envelope.data?.message || '已接受助战')
    pushLog(envelope.data?.message || '已接受助战邀请', 'success')
    await refreshAssist()
  } finally {
    assistBusy.value = false
  }
}

async function onRejectAssist(session: AvatarAssistSessionPublic): Promise<void> {
  assistBusy.value = true
  try {
    const envelope = await rejectAvatarAssist(session.id)
    if (envelope.code !== 0) {
      ElMessage.error(envelope.message || '拒绝失败')
      return
    }
    ElMessage.success(envelope.data?.message || '已拒绝')
    await refreshAssist()
  } finally {
    assistBusy.value = false
  }
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
  await avatarStore.load()
  await refreshAssist()
  pushLog('道友页已就绪：私聊 / 赠礼 / 助战 / 面交；组队请到队伍页。', 'info')
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
      <el-button size="small" @click="router.push('/social')">社交中心</el-button>
      <el-button size="small" @click="router.push('/market?mode=face')">面交台</el-button>
    </div>

    <div class="main-grid">
      <div class="main-left">
        <FriendListPanel show-actions @log="pushLog" />
      </div>
      <aside class="main-side">
        <el-card shadow="never">
          <template #header>
            <el-text tag="b" size="small">我的化身助战</el-text>
          </template>
          <div class="assist-switch">
            <el-switch
              v-model="assistEnabled"
              :loading="assistBusy"
              active-text="允许道友借化身"
              @change="onToggleAssist"
            />
            <el-text size="small" type="info">
              离线时道友可直接借入；在线时需你点接受。助战仅可用于对方 PVE。
            </el-text>
          </div>
        </el-card>

        <el-card v-if="assistIncoming.length" shadow="never">
          <template #header>
            <el-text tag="b" size="small">待处理助战邀请</el-text>
          </template>
          <div
            v-for="s in assistIncoming"
            :key="s.id"
            class="assist-row"
          >
            <el-text size="small">
              {{ s.borrower_name || s.borrower_character_id }} 邀你的化身助战
            </el-text>
            <div class="assist-actions">
              <el-button
                size="small"
                type="primary"
                :loading="assistBusy"
                @click="onAcceptAssist(s)"
              >
                接受
              </el-button>
              <el-button size="small" :loading="assistBusy" @click="onRejectAssist(s)">
                拒绝
              </el-button>
            </div>
          </div>
        </el-card>

        <el-card shadow="never">
          <template #header>
            <el-text tag="b" size="small">道友数</el-text>
          </template>
          <el-text>
            {{ friendsStore.friendCount }} / {{ friendsStore.maxFriends || '—' }}
          </el-text>
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
.friends-page {
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
  grid-template-columns: minmax(0, 1fr) 260px;
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

.assist-switch {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.assist-row {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin-bottom: 0.5rem;
}

.assist-actions {
  display: flex;
  gap: 0.35rem;
}

.log-line {
  margin-bottom: 0.25rem;
}
</style>
