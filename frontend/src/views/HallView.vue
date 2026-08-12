<script setup lang="ts">
/**
 * 修仙大厅（M2）：三向修炼 / 离线领取 / 分配 / 体质 / 突破 / 战斗。
 */
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AllocatePanel from '../components/AllocatePanel.vue'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import BattlePanel from '../components/BattlePanel.vue'
import BreakthroughPanel from '../components/BreakthroughPanel.vue'
import CharacterPanel from '../components/CharacterPanel.vue'
import ConstitutionPanel from '../components/ConstitutionPanel.vue'
import GameLogPanel from '../components/GameLogPanel.vue'
import GmDevPanel from '../components/GmDevPanel.vue'
import HallBattleGate from '../components/HallBattleGate.vue'
import HallDualThreadGate from '../components/hall/HallDualThreadGate.vue'
import HallEnvGate from '../components/hall/HallEnvGate.vue'
import HallDaoGate from '../components/hall/HallDaoGate.vue'
import HallSocialGate from '../components/hall/HallSocialGate.vue'
import EnvModifierHint from '../components/hall/EnvModifierHint.vue'
import DualIdleSummary from '../components/hall/DualIdleSummary.vue'
import ActivityStatusBanner from '../components/hall/ActivityStatusBanner.vue'
import IdlePanel from '../components/IdlePanel.vue'
import OfflineClaimDialog from '../components/OfflineClaimDialog.vue'
import { useAuthStore } from '../stores/auth'
import { useCharacterStore } from '../stores/character'
import { useDaoLordStore } from '../stores/daoLord'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'
import type { IdleSyncData } from '../types/idle'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const characterStore = useCharacterStore()
const daoLordStore = useDaoLordStore()

const loadError = ref('')
/** 事件日志环形缓冲上限，防止战斗刷屏撑爆 DOM */
const MAX_LOG_ENTRIES = 200
const logEntries = ref<GameLogEntry[]>([])
const offlineDialogOpen = ref(false)

function pushLog(
  message: string,
  level: GameLogEntry['level'] = 'info',
): void {
  const next = [...logEntries.value, createLogEntry(message, level)]
  logEntries.value =
    next.length > MAX_LOG_ENTRIES ? next.slice(-MAX_LOG_ENTRIES) : next
}

function onPollSettled(data: IdleSyncData): void {
  // pending 期间不应入账；双保险避免竞态回调写日志
  if (characterStore.hasOfflinePending || data.character.offline_pending) {
    characterStore.stopIdleRealtime()
    return
  }
  const parts: string[] = []
  if (data.gained_cultivation) parts.push(`修为 +${data.gained_cultivation}`)
  if (data.gained_body) parts.push(`炼体度 +${data.gained_body}`)
  if (data.gained_crafting) parts.push(`制造业经验 +${data.gained_crafting}`)
  parts.push(`灵石 -${data.spent_spirit_stones}`)
  pushLog(`修炼结算 ${data.settled_ticks} 片：${parts.join('，')}`, 'success')
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

/**
 * 无 pending 时确保实时调度已启动（领取后 / 无离线进厅）。
 */
function ensureRealtime(): void {
  if (!characterStore.character?.offline_pending) {
    characterStore.startIdleRealtime(onPollSettled)
  } else {
    characterStore.stopIdleRealtime()
  }
}

watch(offlineDialogOpen, (open, wasOpen) => {
  if (wasOpen && !open) {
    ensureRealtime()
  }
})

// pending 出现时立即停表；领取清空后恢复
watch(
  () => characterStore.hasOfflinePending,
  (pending) => {
    if (pending) {
      characterStore.stopIdleRealtime()
    } else if (characterStore.character) {
      ensureRealtime()
    }
  },
)

onMounted(async () => {
  loadError.value = ''
  pushLog('正在连接仙界…', 'system')
  try {
    const ok = await characterStore.fetchMe()
    if (!ok) {
      authStore.setHasCharacter(false)
      await router.replace('/create-character')
      return
    }
    const ch = characterStore.character
    if (ch) {
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
        pushLog('大厅已就绪：大道 · 道主 · 环境 · 渡劫 · 轮回。', 'info')
        ensureRealtime()
      }
      // ?hint=env / dao / social 滚动到对应门闸
      if (route.query.hint === 'env') {
        requestAnimationFrame(() => {
          document.getElementById('hall-env-gate')?.scrollIntoView({ behavior: 'smooth' })
        })
      }
      if (route.query.hint === 'dao') {
        requestAnimationFrame(() => {
          document.getElementById('hall-dao-gate')?.scrollIntoView({ behavior: 'smooth' })
        })
      }
      if (route.query.hint === 'social') {
        requestAnimationFrame(() => {
          document.getElementById('hall-social-gate')?.scrollIntoView({ behavior: 'smooth' })
        })
      }
      // 轻量拉开窗态供 HallDaoGate 角标
      void daoLordStore.refreshWindow()
    }
  } catch (e: unknown) {
    loadError.value = e instanceof Error ? e.message : '加载角色失败'
    pushLog(loadError.value, 'warning')
  }
})

onUnmounted(() => {
  characterStore.stopIdleRealtime()
})
</script>

<template>
  <div class="hall-page">
    <AuthSessionBar />

    <div class="hall-title">
      <el-text tag="b" size="large">修仙大厅</el-text>
      <el-text type="info" size="small">M7 宗门与社交 · 养成枢纽</el-text>
      <div class="hall-nav">
        <el-button size="small" @click="router.push('/formation')">布阵</el-button>
        <el-button size="small" type="danger" @click="router.push('/battle')">战斗</el-button>
        <el-button size="small" type="primary" @click="router.push('/avatar')">化身</el-button>
        <el-button size="small" type="warning" @click="router.push('/workshop')">工坊</el-button>
        <el-button size="small" type="success" @click="router.push('/pets')">灵兽园</el-button>
        <el-button size="small" type="danger" plain @click="router.push('/tribulation')">渡劫</el-button>
        <el-button size="small" plain @click="router.push('/reincarnation')">轮回/祭坛</el-button>
        <el-button size="small" type="primary" plain @click="router.push('/dao')">大道</el-button>
        <el-button size="small" type="danger" plain @click="router.push('/dao-lord')">道主</el-button>
        <el-button size="small" type="success" plain @click="router.push('/sect')">宗门</el-button>
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
        <CharacterPanel :character="characterStore.character" />
        <IdlePanel @log="pushLog" @need-claim-offline="openOfflineDialog" />
        <ActivityStatusBanner />
        <EnvModifierHint kind="idle" />
        <DualIdleSummary />
        <AllocatePanel @log="pushLog" />
        <ConstitutionPanel @log="pushLog" />
        <BreakthroughPanel @log="pushLog" />
        <HallBattleGate />
        <HallDualThreadGate />
        <HallEnvGate />
        <HallDaoGate />
        <HallSocialGate />
        <BattlePanel @log="pushLog" />
        <GmDevPanel @log="pushLog" />
      </aside>
      <main class="hall-main">
        <GameLogPanel :entries="logEntries" />
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
  /* 仅事件日志：半个视口高，滚动时贴顶，溢出在窗内滚 */
  position: sticky;
  top: 0.75rem;
  height: 50vh;
  min-height: 280px;
  display: flex;
  flex-direction: column;
}

@media (max-width: 800px) {
  .hall-grid {
    grid-template-columns: 1fr;
  }

  .hall-main {
    position: relative;
    top: auto;
    height: 50vh;
    min-height: 240px;
  }
}
</style>
