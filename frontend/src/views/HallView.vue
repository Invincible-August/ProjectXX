<script setup lang="ts">
/**
 * 修仙大厅：角色摘要 / 修炼区 / 事件日志。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import CharacterPanel from '../components/CharacterPanel.vue'
import GameLogPanel from '../components/GameLogPanel.vue'
import HallInviteList from '../components/hall/HallInviteList.vue'
import IdlePanel from '../components/IdlePanel.vue'
import OfflineClaimDialog from '../components/OfflineClaimDialog.vue'
import { useAuthStore } from '../stores/auth'
import { useAvatarStore } from '../stores/avatar'
import { useCharacterStore } from '../stores/character'
import { useGameLogStore } from '../stores/gameLog'
import { useResearchStore } from '../stores/research'
import { useWsStore } from '../stores/ws'
import { type GameLogEntry } from '../types/gameLog'
import type { IdleSyncData } from '../types/idle'
import { avatarAsCharacter } from '../utils/avatarAsCharacter'
import {
  addGainChunk,
  chunkFromIdleSync,
  emptyGainChunk,
  flushGainChunk,
  formatIdleSettleLine,
  takeSettleChunks,
  type IdleGainChunk,
} from '../utils/idleSettleLog'

const router = useRouter()
const authStore = useAuthStore()
const characterStore = useCharacterStore()
const avatarStore = useAvatarStore()
const gameLogStore = useGameLogStore()
const researchStore = useResearchStore()
const wsStore = useWsStore()

const loadError = ref('')
const offlineDialogOpen = ref(false)
const briefTab = ref<'main' | 'avatar'>('main')

const hasAvatar = computed(
  () => Boolean(characterStore.character?.has_avatar) || Boolean(avatarStore.avatar),
)

const hallBriefCharacter = computed(() => {
  const ch = characterStore.character
  if (!ch) return null
  if (briefTab.value !== 'avatar') return ch
  const av = avatarStore.avatar
  if (!av) return ch
  return avatarAsCharacter(ch, av)
})

const draftResumeHint = computed(() => {
  const row = researchStore.openSessions[0]
  if (!row) return ''
  return `有进行中的${row.kind_label_zh}草案，可点「继续草案」。`
})

function pushLog(
  message: string,
  level: GameLogEntry['level'] = 'info',
): void {
  gameLogStore.push(message, level)
}

const mainSettleBuf: IdleGainChunk = emptyGainChunk()
const avatarSettleBuf: IdleGainChunk = emptyGainChunk()

function ingestSettle(
  who: 'main' | 'avatar',
  chunk: IdleGainChunk,
  stopped: boolean,
): void {
  const buf = who === 'main' ? mainSettleBuf : avatarSettleBuf
  if (chunk.ticks > 0) addGainChunk(buf, chunk)
  if (stopped) {
    const rest = flushGainChunk(buf)
    if (rest) {
      const line = formatIdleSettleLine(who, rest, true)
      if (line) pushLog(line, 'success')
    } else {
      pushLog(who === 'main' ? '本体停止修炼' : '化身停止修炼', 'info')
    }
    return
  }
  for (const piece of takeSettleChunks(buf)) {
    const line = formatIdleSettleLine(who, piece, false)
    if (line) pushLog(line, 'success')
  }
}

function onPollSettled(data: IdleSyncData): void {
  // pending 期间不应入账；双保险避免竞态回调写日志
  if (characterStore.hasOfflinePending || data.character.offline_pending) {
    return
  }
  const miningStones = Number(data.gained_mining_stones || 0)
  const miningPool = Number(data.mining_pool_stones || 0)
  const spentStamina = Number(data.spent_stamina || 0)
  if (miningStones > 0 || spentStamina > 0 || miningPool > 0) {
    const parts: string[] = []
    if (miningStones > 0) parts.push(`个人灵石 +${miningStones}`)
    if (spentStamina > 0) parts.push(`体力 -${spentStamina}`)
    if (miningPool > 0) parts.push(`宗门库 +${miningPool}`)
    pushLog(
      `采矿结算 ${data.settled_ticks} 周天：${parts.join('，') || '无收益'}`,
      'success',
    )
    ingestSettle('avatar', chunkFromIdleSync(data.avatar_gains || {}), false)
    return
  }
  ingestSettle('main', chunkFromIdleSync(data), false)
  ingestSettle('avatar', chunkFromIdleSync(data.avatar_gains || {}), false)
  if (data.character.is_stalled) {
    pushLog('灵石不足，修炼停滞；可通过战斗获取灵石。', 'warning')
  }
}

function onMainSettleTick(data: IdleSyncData): void {
  ingestSettle('main', chunkFromIdleSync(data), false)
  ingestSettle('avatar', chunkFromIdleSync(data.avatar_gains || {}), false)
}

function onMainSettleStop(data: IdleSyncData): void {
  ingestSettle('main', chunkFromIdleSync(data), true)
  ingestSettle('avatar', chunkFromIdleSync(data.avatar_gains || {}), false)
}

function onAvatarSettleTick(gains: IdleSyncData['avatar_gains']): void {
  ingestSettle('avatar', chunkFromIdleSync(gains || {}), false)
}

function onAvatarSettleStop(gains: IdleSyncData['avatar_gains']): void {
  ingestSettle('avatar', chunkFromIdleSync(gains || {}), true)
}

function continueResearchDraft(): void {
  const row = researchStore.openSessions[0]
  if (!row) return
  void router.push({
    path: '/cave/lab',
    query: { mode: row.kind, session: String(row.id) },
  })
}

function openOfflineDialog(): void {
  offlineDialogOpen.value = true
}

function autoOpenOfflineEnabled(): boolean {
  const raw = import.meta.env.VITE_OFFLINE_AUTO_OPEN
  if (raw === undefined || raw === '') return true
  return String(raw).toLowerCase() !== 'false'
}

watch(offlineDialogOpen, (open, wasOpen) => {
  if (wasOpen && !open && !characterStore.hasOfflinePending) {
    // 领取关闭后由 playShell 级 realtime 自行恢复；此处仅确保回调仍在
    characterStore.setIdleSettledCallback(onPollSettled)
  }
})

// pending 出现时停大厅日志回调侧不额外 stop 全局 sync（store 已处理）
watch(
  () => characterStore.hasOfflinePending,
  (pending) => {
    if (!pending && characterStore.character) {
      characterStore.setIdleSettledCallback(onPollSettled)
    }
  },
)

watch(hasAvatar, (ready) => {
  if (!ready) briefTab.value = 'main'
})

watch(briefTab, (tab) => {
  if (tab === 'avatar' && !avatarStore.avatar) void avatarStore.load()
})

onMounted(async () => {
  loadError.value = ''
  characterStore.setIdleSettledCallback(onPollSettled)

  // 玩法壳内 WS 已由 App 长连接保活；大厅首屏只欢迎一次，避免切页刷「正在连接仙界…」
  const firstVisit = !gameLogStore.hallBootstrapped
  if (firstVisit) {
    if (wsStore.status !== 'open') {
      pushLog('正在连接仙界…', 'system')
    }
    gameLogStore.markHallBootstrapped()
  }

  try {
    const ok = await characterStore.fetchMe()
    if (!ok) {
      authStore.setHasCharacter(false)
      await router.replace('/create-character')
      return
    }
    const ch = characterStore.character
    if (!ch) return
    await researchStore.loadOpenSessions()
    if (ch.has_avatar) {
      await avatarStore.load()
    }

    if (firstVisit) {
      pushLog(`欢迎回来，${ch.name}。`, 'success')
      pushLog(
        `当前境界：${ch.realm_display} · 品阶 ${ch.breakthrough_grade_name} · 灵石 ${ch.spirit_stones}`,
        'info',
      )
      pushLog(
        `攻防 ${ch.base_atk}/${ch.base_hp} · 修炼方向：${ch.idle_direction_name}`,
        'info',
      )
      if (ch.is_stalled) {
        pushLog('灵石不足，修炼停滞；可通过战斗获取灵石。', 'warning')
      }
      if (ch.offline_pending) {
        pushLog('检测到未领取离线收益。', 'warning')
        if (autoOpenOfflineEnabled()) {
          offlineDialogOpen.value = true
        }
      } else {
        pushLog('大厅已就绪：角色 · 修炼 · 工坊 · 洞府 · 宗门 · 社交 · 商店；右侧有邀请列表。', 'info')
      }
    } else if (ch.offline_pending && autoOpenOfflineEnabled()) {
      offlineDialogOpen.value = true
    }
  } catch (e: unknown) {
    loadError.value = e instanceof Error ? e.message : '加载角色失败'
    pushLog(loadError.value, 'warning')
  }
})

onUnmounted(() => {
  // 离开大厅不停挂机 sync（由玩法壳管生命周期）；仅解绑日志回调
  characterStore.setIdleSettledCallback(null)
})
</script>

<template>
  <div class="hall-page">
    <AuthSessionBar />
    <div class="hall-title">
      <el-text tag="b" size="large">修仙大厅</el-text>
      <el-text type="info" size="small">养成枢纽</el-text>
      <el-button
        v-if="researchStore.openSessions.length"
        type="warning"
        size="small"
        class="offline-btn"
        @click="continueResearchDraft"
      >
        继续草案
      </el-button>
      <el-button
        v-if="characterStore.hasOfflinePending"
        type="warning"
        size="small"
        class="offline-btn"
        @click="openOfflineDialog"
      >
        领取离线收益
      </el-button>
    </div>

    <el-alert
      v-if="draftResumeHint"
      :title="draftResumeHint"
      type="info"
      show-icon
      :closable="false"
      class="hall-alert"
    />

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
      class="hall-alert"
    />

    <el-skeleton v-if="characterStore.loading && !characterStore.character" animated :rows="6" />

    <div v-else class="hall-grid">
      <aside class="hall-side">
        <CharacterPanel
          :character="hallBriefCharacter"
          compact
          :variant="briefTab"
          :show-brief-switch="hasAvatar"
          :brief-tab="briefTab"
          @update:brief-tab="briefTab = $event"
        />
        <IdlePanel
          @log="pushLog"
          @need-claim-offline="openOfflineDialog"
          @settle-tick="onMainSettleTick"
          @settle-stop="onMainSettleStop"
          @avatar-settle-tick="onAvatarSettleTick"
          @avatar-settle-stop="onAvatarSettleStop"
        />
      </aside>
      <main class="hall-main">
        <GameLogPanel :entries="gameLogStore.entries" />
        <HallInviteList />
      </main>
    </div>

    <OfflineClaimDialog
      v-model="offlineDialogOpen"
      @log="pushLog"
    />
  </div>
</template>

<style scoped>
.hall-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 1rem 1rem 2rem;
}

.hall-title {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.5rem 0.75rem;
  margin: 0.75rem 0 1rem;
}

.offline-btn {
  margin-left: auto;
}

.hall-alert {
  margin-bottom: 1rem;
}

.hall-grid {
  display: grid;
  /* 左侧操作区恢复原宽；右侧仅日志半窗高 */
  grid-template-columns: minmax(280px, 380px) 1fr;
  gap: 1rem;
  align-items: start;
}

.hall-side {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.hall-main {
  min-width: 0;
  position: sticky;
  top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  /* 日志半窗 + 邀请列表 */
  max-height: calc(50vh + 280px);
}

.hall-main :deep(.game-log-panel),
.hall-main :deep(.log-panel) {
  height: 50vh;
  min-height: 280px;
}

@media (max-width: 800px) {
  .hall-grid {
    grid-template-columns: 1fr;
  }

  .hall-main {
    position: relative;
    top: auto;
    max-height: none;
  }

  .hall-main :deep(.log-panel) {
    height: 40vh;
    min-height: 220px;
  }
}
</style>
