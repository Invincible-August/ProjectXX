<script setup lang="ts">
/**
 * 拍卖行页（原 /market 交易行+拍卖+面交）：亦可由商店中心 mode=auction 嵌入。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import AuctionPanel from '../components/market/AuctionPanel.vue'
import FaceTradePanel from '../components/market/FaceTradePanel.vue'
import TradeListingPanel from '../components/market/TradeListingPanel.vue'
import { useCharacterStore } from '../stores/character'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'

/** 合法 mode：一口价交易行 / 拍卖 / 面交 */
type AuctionHouseMode = 'listings' | 'auction' | 'face'

const MODE_SET = new Set<string>(['listings', 'auction', 'face'])

const props = withDefaults(
  defineProps<{
    /** 嵌入商店中心时隐藏顶栏与回大厅 */
    embedded?: boolean
  }>(),
  { embedded: false },
)

const route = useRoute()
const router = useRouter()
const characterStore = useCharacterStore()

const loadError = ref('')
const logEntries = ref<GameLogEntry[]>([])

const mode = computed<AuctionHouseMode>(() => {
  if (props.embedded) {
    const s = route.query.sub
    if (typeof s === 'string' && MODE_SET.has(s)) {
      return s as AuctionHouseMode
    }
    return 'listings'
  }
  const m = route.query.mode
  if (typeof m === 'string' && MODE_SET.has(m)) {
    return m as AuctionHouseMode
  }
  return 'listings'
})

/** 面交 peer 预填（角色 id 或道号） */
const facePeer = computed(() => {
  const p = route.query.peer
  return typeof p === 'string' ? p : null
})

/** 面交会话 id 深链 */
const faceSessionId = computed(() => {
  const s = route.query.session
  if (typeof s === 'string' && /^\d+$/.test(s)) {
    return Number(s)
  }
  return null
})

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logEntries.value = [...logEntries.value.slice(-49), createLogEntry(message, level)]
}

function setMode(next: AuctionHouseMode): void {
  if (props.embedded) {
    const query: Record<string, string> = {
      ...(route.query as Record<string, string>),
      mode: 'auction',
      sub: next,
    }
    if (next !== 'face') {
      delete query.peer
      delete query.session
    }
    void router.replace({ query })
    return
  }
  const query: Record<string, string> = {
    ...(route.query as Record<string, string>),
    mode: next,
  }
  if (next !== 'face') {
    delete query.peer
    delete query.session
  }
  void router.replace({ query })
}

/**
 * 面交会话 id 回写 query，便于刷新/分享。
 *
 * @param sessionId - 会话 id 或 null
 */
function onFaceSessionChange(sessionId: number | null): void {
  const query: Record<string, string> = {
    ...(route.query as Record<string, string>),
  }
  if (props.embedded) {
    query.mode = 'auction'
    query.sub = 'face'
  } else {
    query.mode = 'face'
  }
  if (sessionId != null && sessionId > 0) {
    query.session = String(sessionId)
  } else {
    delete query.session
  }
  void router.replace({ query })
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
  pushLog('拍卖行已就绪：一口价 / 竞拍 / 面交以服务端为准。', 'info')
  if (!props.embedded) {
    if (!MODE_SET.has(String(route.query.mode ?? ''))) {
      void router.replace({ query: { ...route.query, mode: 'listings' } })
    }
  } else if (!MODE_SET.has(String(route.query.sub ?? 'listings'))) {
    void router.replace({
      query: { ...route.query, mode: 'auction', sub: 'listings' },
    })
  }
})

watch(
  () => [route.query.mode, route.query.sub],
  () => {
    // mode 切换时保留侧栏日志即可
  },
)
</script>

<template>
  <div class="market-page" :class="{ embedded }">
    <AuthSessionBar v-if="!embedded" />

    <div v-if="!embedded" class="page-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-button size="small" @click="router.push('/shop?mode=auction')">商店 · 拍卖行</el-button>
      <el-text tag="b" size="large">拍卖行</el-text>
      <el-text type="info" size="small">一口价 · 竞拍 · 面交</el-text>
      <div class="mode-nav">
        <el-button
          size="small"
          :type="mode === 'listings' ? 'primary' : 'default'"
          @click="setMode('listings')"
        >
          一口价
        </el-button>
        <el-button
          size="small"
          :type="mode === 'auction' ? 'primary' : 'default'"
          @click="setMode('auction')"
        >
          竞拍
        </el-button>
        <el-button
          size="small"
          :type="mode === 'face' ? 'primary' : 'default'"
          @click="setMode('face')"
        >
          面交
        </el-button>
      </div>
    </div>
    <div v-else class="mode-nav embedded-nav">
      <el-button
        size="small"
        :type="mode === 'listings' ? 'primary' : 'default'"
        @click="setMode('listings')"
      >
        一口价
      </el-button>
      <el-button
        size="small"
        :type="mode === 'auction' ? 'primary' : 'default'"
        @click="setMode('auction')"
      >
        竞拍
      </el-button>
      <el-button
        size="small"
        :type="mode === 'face' ? 'primary' : 'default'"
        @click="setMode('face')"
      >
        面交
      </el-button>
    </div>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
      class="page-alert"
    />

    <div class="main-grid">
      <div class="main-left">
        <TradeListingPanel v-if="mode === 'listings'" @log="pushLog" />
        <AuctionPanel v-else-if="mode === 'auction'" @log="pushLog" />
        <FaceTradePanel
          v-else
          :peer="facePeer"
          :session-id="faceSessionId"
          @log="pushLog"
          @session-change="onFaceSessionChange"
        />
      </div>
      <aside class="main-side">
        <el-card v-if="logEntries.length" shadow="never">
          <template #header>
            <el-text tag="b" size="small">本页日志</el-text>
          </template>
          <div v-for="e in logEntries.slice(-8)" :key="e.id" class="log-line">
            <el-text size="small">{{ e.message }}</el-text>
          </div>
        </el-card>
        <el-card shadow="never">
          <template #header>
            <el-text tag="b" size="small">灵石</el-text>
          </template>
          <el-text>
            {{ characterStore.character?.spirit_stones ?? '—' }}
          </el-text>
        </el-card>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.market-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 1rem 1rem 2rem;
}

.market-page.embedded {
  max-width: none;
  margin: 0;
  padding: 0;
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

.embedded-nav {
  margin: 0 0 0.75rem;
  margin-left: 0;
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

.log-line {
  padding: 0.15rem 0;
}

@media (max-width: 800px) {
  .main-grid {
    grid-template-columns: 1fr;
  }
}
</style>
