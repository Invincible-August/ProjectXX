<script setup lang="ts">
/**
 * 拍卖行页（一口价 + 竞拍）：亦可由商店中心 mode=auction 嵌入。
 * 道友交易已迁入社交页 /social?mode=trade。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import AuctionPanel from '../components/market/AuctionPanel.vue'
import TradeListingPanel from '../components/market/TradeListingPanel.vue'
import { useCharacterStore } from '../stores/character'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'

/** 合法 mode：一口价交易行 / 拍卖 */
type AuctionHouseMode = 'listings' | 'auction'

const MODE_SET = new Set<string>(['listings', 'auction'])

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

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logEntries.value = [...logEntries.value.slice(-49), createLogEntry(message, level)]
}

function setMode(next: AuctionHouseMode): void {
  if (props.embedded) {
    void router.replace({
      query: {
        ...(route.query as Record<string, string>),
        mode: 'auction',
        sub: next,
      },
    })
    return
  }
  void router.replace({
    query: {
      ...(route.query as Record<string, string>),
      mode: next,
    },
  })
}

function redirectLegacyFace(): void {
  const faceHit =
    route.query.mode === 'face' ||
    route.query.sub === 'face' ||
    (typeof route.query.session === 'string' && props.embedded && route.query.sub === 'face')
  if (!faceHit && route.query.mode !== 'face' && route.query.sub !== 'face') {
    return
  }
  if (route.query.mode !== 'face' && route.query.sub !== 'face') return
  const peer = typeof route.query.peer === 'string' ? route.query.peer : undefined
  const session = typeof route.query.session === 'string' ? route.query.session : undefined
  void router.replace({
    path: '/social',
    query: {
      mode: 'trade',
      ...(peer ? { peer } : {}),
      ...(session ? { session } : {}),
    },
  })
}

onMounted(async () => {
  loadError.value = ''
  redirectLegacyFace()
  if (!characterStore.character) {
    const ok = await characterStore.fetchMe()
    if (!ok) {
      await router.replace('/create-character')
      return
    }
  }
  pushLog('拍卖行已就绪：一口价 / 竞拍以服务端为准；道友交易见社交。', 'info')
  if (!props.embedded) {
    if (!MODE_SET.has(String(route.query.mode ?? ''))) {
      if (route.query.mode !== 'face') {
        void router.replace({ query: { ...route.query, mode: 'listings' } })
      }
    }
  } else if (!MODE_SET.has(String(route.query.sub ?? 'listings'))) {
    if (route.query.sub !== 'face') {
      void router.replace({
        query: { ...route.query, mode: 'auction', sub: 'listings' },
      })
    }
  }
})

watch(
  () => [route.query.mode, route.query.sub],
  () => {
    redirectLegacyFace()
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
      <el-text type="info" size="small">一口价 · 竞拍</el-text>
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
        <AuctionPanel v-else @log="pushLog" />
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
  width: 100%;
}
.embedded-nav {
  margin-bottom: 0.75rem;
}
.page-alert {
  margin-bottom: 1rem;
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
