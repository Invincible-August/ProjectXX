<script setup lang="ts">
/**
 * 悟道页（/dao）：开道 / 道池。仅真仙可进；actor=main|avatar 各走独立道。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import DaoOpenPanel from '../components/dao/DaoOpenPanel.vue'
import DaoPoolGallery from '../components/dao/DaoPoolGallery.vue'
import DaoRestraintHint from '../components/dao/DaoRestraintHint.vue'
import DaoStatusPanel from '../components/dao/DaoStatusPanel.vue'
import DaoUsageToggle from '../components/dao/DaoUsageToggle.vue'
import type { DaoActor } from '../api/dao'
import { useAvatarStore } from '../stores/avatar'
import { useCharacterStore } from '../stores/character'
import { useDaoStore } from '../stores/dao'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'
import { canEnterWudao } from '../utils/realm'

const route = useRoute()
const router = useRouter()
const characterStore = useCharacterStore()
const avatarStore = useAvatarStore()
const daoStore = useDaoStore()

const loadError = ref('')
const logEntries = ref<GameLogEntry[]>([])

const actor = computed<DaoActor>(() =>
  route.query.actor === 'avatar' ? 'avatar' : 'main',
)

const mode = computed(() => {
  const m = route.query.mode
  return m === 'pool' || m === 'open' ? m : 'open'
})

const focusId = computed(() =>
  typeof route.query.focus === 'string' ? route.query.focus : null,
)

const backPath = computed(() => (actor.value === 'avatar' ? '/avatar' : '/character'))

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logEntries.value = [...logEntries.value.slice(-49), createLogEntry(message, level)]
}

function setMode(next: 'open' | 'pool'): void {
  void router.replace({ query: { ...route.query, mode: next } })
}

async function ensureRealmOrLeave(): Promise<boolean> {
  if (!characterStore.character) {
    const ok = await characterStore.fetchMe()
    if (!ok) {
      await router.replace('/create-character')
      return false
    }
  }
  if (actor.value === 'avatar') {
    if (!avatarStore.avatar) {
      await avatarStore.load()
    }
    if (!canEnterWudao(avatarStore.avatar?.major_realm)) {
      await router.replace('/avatar')
      return false
    }
    return true
  }
  if (!canEnterWudao(characterStore.character?.major_realm)) {
    await router.replace('/character')
    return false
  }
  return true
}

onMounted(async () => {
  loadError.value = ''
  const ok = await ensureRealmOrLeave()
  if (!ok) return
  daoStore.setPageActor(actor.value)
  if (actor.value === 'main') {
    daoStore.applyMeFromCharacter()
  }
  const err = await daoStore.refresh()
  if (err) {
    loadError.value = err
    pushLog(err, 'warning')
  } else {
    pushLog(
      actor.value === 'avatar' ? '化身悟道页已就绪。' : '本体悟道页已就绪。',
      'info',
    )
  }
  daoStore.startPoll()
})

onUnmounted(() => {
  daoStore.stopPoll()
  daoStore.setPageActor('main')
  daoStore.clearOpening()
})

watch(actor, async (next) => {
  daoStore.setPageActor(next)
  const ok = await ensureRealmOrLeave()
  if (!ok) return
  const err = await daoStore.refresh()
  if (err) loadError.value = err
})
</script>

<template>
  <div class="dao-page">
    <AuthSessionBar />

    <div class="page-title">
      <el-button size="small" @click="router.push(backPath)">
        ← {{ actor === 'avatar' ? '化身' : '角色' }}
      </el-button>
      <el-text tag="b" size="large">悟道</el-text>
      <el-text type="info" size="small">
        {{ actor === 'avatar' ? '化身独立本命道' : '本体本命道' }}
      </el-text>
      <div class="mode-nav">
        <el-button
          size="small"
          :type="mode === 'open' ? 'primary' : 'default'"
          @click="setMode('open')"
        >
          开道
        </el-button>
        <el-button
          size="small"
          :type="mode === 'pool' ? 'primary' : 'default'"
          @click="setMode('pool')"
        >
          道池图鉴
        </el-button>
        <el-button
          v-if="actor === 'main'"
          size="small"
          @click="router.push('/dao-lord')"
        >
          道主
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
      class="page-alert"
    />

    <DaoStatusPanel :dao="daoStore.me" />

    <div class="main-grid">
      <div class="main-left">
        <DaoOpenPanel
          v-if="mode === 'open'"
          @log="pushLog"
          @chosen="pushLog(daoStore.lastMessage || '开道成功', 'success')"
        />
        <DaoPoolGallery
          v-else
          :catalog="daoStore.catalog"
          :focus-id="focusId"
        />
      </div>
      <aside class="main-side">
        <DaoRestraintHint />
        <DaoUsageToggle v-if="actor === 'main'" />
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

    <DaoPoolGallery
      v-if="mode === 'open'"
      class="pool-below"
      :catalog="daoStore.catalog"
      :focus-id="focusId"
    />
  </div>
</template>

<style scoped>
.dao-page {
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
  margin-left: auto;
}

.page-alert {
  margin-bottom: 0.75rem;
}

.main-grid {
  display: grid;
  grid-template-columns: 1fr minmax(220px, 300px);
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.main-left,
.main-side {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-width: 0;
}

.pool-below {
  margin-top: 0.75rem;
}

.log-line {
  padding: 0.15rem 0;
}

@media (max-width: 800px) {
  .main-grid {
    grid-template-columns: 1fr;
  }
}
</style>
