<script setup lang="ts">
/**
 * 修仙大厅：角色摘要 / 修炼区 / 事件日志。
 */
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import CharacterPanel from '../components/CharacterPanel.vue'
import GameLogPanel from '../components/GameLogPanel.vue'
import HallInviteList from '../components/hall/HallInviteList.vue'
import IdlePanel from '../components/IdlePanel.vue'
import OfflineClaimDialog from '../components/OfflineClaimDialog.vue'
import { useAuthStore } from '../stores/auth'
import { useCharacterStore } from '../stores/character'
import { useGameLogStore } from '../stores/gameLog'
import { useWsStore } from '../stores/ws'
import { type GameLogEntry } from '../types/gameLog'
import type { IdleSyncData } from '../types/idle'

const router = useRouter()
const authStore = useAuthStore()
const characterStore = useCharacterStore()
const gameLogStore = useGameLogStore()
const wsStore = useWsStore()

const loadError = ref('')
const offlineDialogOpen = ref(false)

function pushLog(
  message: string,
  level: GameLogEntry['level'] = 'info',
): void {
  gameLogStore.push(message, level)
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
    return
  }
  if (!data.settled_ticks) return
  const parts: string[] = []
  if (data.gained_cultivation) parts.push(`修为 +${data.gained_cultivation}`)
  if (data.gained_body) parts.push(`淬体度 +${data.gained_body}`)
  if (data.gained_crafting) parts.push(`制造业经验 +${data.gained_crafting}`)
  if (data.spent_spirit_stones) parts.push(`灵石 -${data.spent_spirit_stones}`)
  pushLog(
    `修炼结算 ${data.settled_ticks} 周天：${parts.join('，') || '无收益'}`,
    'success',
  )
  if (data.character.is_stalled) {
    pushLog('灵石不足，修炼停滞；可通过战斗获取灵石。', 'warning')
  }
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
        pushLog('大厅已就绪：角色 · 修炼 · 宗门 · 社交 · 商店；右侧有邀请列表。', 'info')
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
    <div class="hall-title">
      <el-text tag="b" size="large">修仙大厅</el-text>
      <el-text type="info" size="small">养成枢纽</el-text>
      <div class="hall-nav">
        <el-button size="small" type="primary" plain @click="router.push('/character')">
          角色
        </el-button>
        <el-button size="small" @click="router.push('/formation')">布阵</el-button>
        <el-button size="small" type="danger" @click="router.push('/battle')">战斗</el-button>
        <el-button size="small" type="warning" @click="router.push('/avatar')">化身</el-button>
        <el-button size="small" type="success" plain @click="router.push('/sect')">宗门</el-button>
        <el-button size="small" type="primary" @click="router.push('/social')">社交</el-button>
        <el-button size="small" type="warning" plain @click="router.push('/shop')">商店</el-button>
        <el-button size="small" @click="router.push('/account')">账号</el-button>
      </div>
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
        <CharacterPanel :character="characterStore.character" compact />
        <IdlePanel @log="pushLog" @need-claim-offline="openOfflineDialog" />
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

.hall-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  width: 100%;
}

@media (min-width: 801px) {
  .hall-nav {
    width: auto;
    margin-left: auto;
  }
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
