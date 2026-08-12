<script setup lang="ts">
/**
 * 化身页：凝练 / 功能看板 / 挂机 / 传修为 / 体力 / 神识 / 探索·任务桩入口。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import AvatarCondensePanel from '../components/avatar/AvatarCondensePanel.vue'
import AvatarFeaturesPanel from '../components/avatar/AvatarFeaturesPanel.vue'
import AvatarIdlePanel from '../components/avatar/AvatarIdlePanel.vue'
import AvatarStaminaPanel from '../components/avatar/AvatarStaminaPanel.vue'
import AvatarTransferPanel from '../components/avatar/AvatarTransferPanel.vue'
import DivineSenseBar from '../components/avatar/DivineSenseBar.vue'
import { acceptAvatarQuest, fetchExploreStatus } from '../api/avatar'
import { useAvatarStore } from '../stores/avatar'
import { useCharacterStore } from '../stores/character'
import type { GameLogEntry } from '../types/gameLog'
import { createLogEntry } from '../types/gameLog'

const route = useRoute()
const router = useRouter()
const avatarStore = useAvatarStore()
const characterStore = useCharacterStore()

const loadError = ref('')
const logEntries = ref<GameLogEntry[]>([])
const exploreHint = ref('')

const hasAvatar = computed(
  () => Boolean(avatarStore.avatar) || Boolean(characterStore.character?.has_avatar),
)
const avatar = computed(() => avatarStore.avatar)
const sense = computed(() => avatarStore.sense ?? characterStore.character?.divine_sense ?? null)
const features = computed(
  () => avatar.value?.features ?? avatarStore.features?.features ?? [],
)
const unlockPreview = computed(
  () => avatar.value?.unlock_preview ?? avatarStore.features?.unlock_preview ?? null,
)
const majorRealm = computed(() => characterStore.character?.major_realm ?? '')
/** M5：渡劫真态——化身不可上阵，挂机仍可用 */
const inTribulation = computed(
  () => characterStore.character?.status === 'tribulation',
)
const workshopUnlocked = computed(
  () => features.value.find((f) => f.feature_id === 'workshop_actor')?.unlocked ?? false,
)
const soloUnlocked = computed(
  () => features.value.find((f) => f.feature_id === 'solo_battle')?.unlocked ?? false,
)

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logEntries.value = [...logEntries.value.slice(-49), createLogEntry(message, level)]
}

async function loadExplore(): Promise<void> {
  if (!hasAvatar.value) return
  const envelope = await fetchExploreStatus()
  if (envelope.code === 0 && envelope.data) {
    exploreHint.value = envelope.data.message
  }
}

async function onQuest(kind: 'npc' | 'sect'): Promise<void> {
  const envelope = await acceptAvatarQuest(kind)
  if (envelope.code !== 0) {
    ElMessage.error(envelope.message || '任务闸拒绝')
    pushLog(envelope.message || '任务未解锁', 'warning')
    return
  }
  const msg = envelope.data?.message || '任务桩'
  ElMessage.info(msg)
  pushLog(msg, 'info')
  if (envelope.data?.avatar) {
    avatarStore.setAvatar(envelope.data.avatar)
  }
}

onMounted(async () => {
  loadError.value = ''
  if (!characterStore.character) {
    const ok = await characterStore.fetchMe()
    if (!ok) {
      await router.replace('/create-character')
      return
    }
  }
  const [avErr, senseErr] = await Promise.all([
    avatarStore.load(),
    avatarStore.loadSense(),
  ])
  if (avErr) loadError.value = avErr
  if (senseErr) pushLog(senseErr, 'warning')
  // 未凝练必须拉 /features（含 condense 权威闸）；已凝练则 /me 已带 features 时可省
  const needFeatures =
    !avatarStore.avatar ||
    !avatarStore.features?.features?.length ||
    !avatarStore.features?.condense
  if (needFeatures) {
    await avatarStore.loadFeatures()
  }
  // 探索桩仅在已解锁 explore_proxy 时拉取（省未解锁角色的往返）
  const exploreUnlocked = features.value.some(
    (f) => f.feature_id === 'explore_proxy' && f.unlocked,
  )
  if (exploreUnlocked) {
    await loadExplore()
  }

  if (route.query.tab === 'transfer') {
    requestAnimationFrame(() => {
      document.getElementById('transfer-panel')?.scrollIntoView({ behavior: 'smooth' })
    })
  }
})
</script>

<template>
  <div class="avatar-page">
    <AuthSessionBar />

    <div class="page-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-text tag="b" size="large">化身</el-text>
      <el-text type="info" size="small">单化身 · 境界功能解锁</el-text>
    </div>

    <DivineSenseBar :sense="sense" />

    <el-alert
      v-if="inTribulation"
      title="渡劫中：化身不可上阵，挂机仍可用"
      type="warning"
      show-icon
      :closable="false"
      class="page-alert"
    />

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
      class="page-alert"
    />

    <div class="avatar-grid">
      <section class="avatar-main">
        <AvatarFeaturesPanel
          v-if="features.length"
          :features="features"
          :unlock-preview="unlockPreview"
          :major-realm="majorRealm"
        />

        <AvatarCondensePanel v-if="!hasAvatar" @log="pushLog" />
        <template v-else-if="avatar">
          <el-card shadow="never" class="status-card">
            <el-text tag="b">{{ avatar.name }}</el-text>
            <el-tag size="small" type="info">{{ avatar.status }}</el-tag>
            <el-text size="small" type="info">
              攻防 {{ avatar.base_stats.atk ?? '?' }}/{{ avatar.base_stats.hp ?? '?' }}
            </el-text>
          </el-card>

          <AvatarStaminaPanel v-if="avatar.stamina" :stamina="avatar.stamina" />
          <AvatarIdlePanel :avatar="avatar" :features="features" @log="pushLog" />
          <AvatarTransferPanel :avatar="avatar" @log="pushLog" />

          <el-card shadow="never">
            <template #header>
              <el-text tag="b">出战与探索</el-text>
            </template>
            <el-text size="small" type="info" class="block-hint">
              {{
                soloUnlocked
                  ? '已解锁化身独战：布阵可不含本体。'
                  : avatar.battle_modes?.solo_battle_hint || '化神后方可化身独战'
              }}
            </el-text>
            <el-text v-if="exploreHint" size="small" type="info" class="block-hint">
              {{ exploreHint }}
            </el-text>
            <div class="link-row">
              <el-button
                size="small"
                :disabled="!workshopUnlocked"
                @click="router.push('/workshop?actor=avatar')"
              >
                去工坊·化身队列
              </el-button>
              <el-button size="small" @click="router.push('/formation')">去布阵</el-button>
              <el-button size="small" @click="onQuest('npc')">NPC 任务（桩）</el-button>
              <el-button size="small" @click="onQuest('sect')">宗门任务（桩）</el-button>
            </div>
          </el-card>
        </template>
        <el-skeleton v-else animated :rows="4" />
      </section>

      <aside v-if="logEntries.length" class="avatar-log">
        <el-card shadow="never">
          <template #header>
            <el-text tag="b" size="small">本页日志</el-text>
          </template>
          <div v-for="entry in logEntries" :key="entry.id" class="log-line">
            <el-text size="small" :type="entry.level === 'warning' ? 'warning' : undefined">
              {{ entry.message }}
            </el-text>
          </div>
        </el-card>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.avatar-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 1rem 1rem 2rem;
}

.page-title {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  margin: 0.75rem 0 1rem;
  flex-wrap: wrap;
}

.page-alert {
  margin-bottom: 1rem;
}

.avatar-grid {
  display: grid;
  grid-template-columns: 1fr minmax(180px, 240px);
  gap: 1rem;
  align-items: start;
}

.avatar-main {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.status-card :deep(.el-card__body) {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}

.link-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.block-hint {
  display: block;
  margin-bottom: 0.35rem;
}

.log-line {
  margin-bottom: 0.25rem;
}

@media (max-width: 700px) {
  .avatar-grid {
    grid-template-columns: 1fr;
  }
}
</style>
