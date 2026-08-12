<script setup lang="ts">
/**
 * 宗门页（M7 L1 + M7-V+ · /sect）：拜入 / 总览 / 议事厅 / 十设施 / 任务 / 商店 / 魂灯 / 兑宠。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import SectCouncilPanel from '../components/sect/SectCouncilPanel.vue'
import SectFormationPanel from '../components/sect/SectFormationPanel.vue'
import SectHerbPanel from '../components/sect/SectHerbPanel.vue'
import SectJoinCreatePanel from '../components/sect/SectJoinCreatePanel.vue'
import SectMinePanel from '../components/sect/SectMinePanel.vue'
import SectOverviewPanel from '../components/sect/SectOverviewPanel.vue'
import SectPetExchangePanel from '../components/sect/SectPetExchangePanel.vue'
import SectQuestPanel from '../components/sect/SectQuestPanel.vue'
import SectScripturePanel from '../components/sect/SectScripturePanel.vue'
import SectShopPanel from '../components/sect/SectShopPanel.vue'
import SectSoulLampPanel from '../components/sect/SectSoulLampPanel.vue'
import SectStatusPanel from '../components/sect/SectStatusPanel.vue'
import SectTreasuryPanel from '../components/sect/SectTreasuryPanel.vue'
import SectWorkshopPanel from '../components/sect/SectWorkshopPanel.vue'
import { useCharacterStore } from '../stores/character'
import { useSectStore } from '../stores/sect'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'

type SectMode =
  | 'join'
  | 'status'
  | 'overview'
  | 'council'
  | 'quests'
  | 'shop'
  | 'treasure'
  | 'scripture'
  | 'forge'
  | 'alchemy'
  | 'talisman'
  | 'formation'
  | 'mine'
  | 'herbs'
  | 'lamps'
  | 'exchange'

const MODE_SET = new Set<string>([
  'join',
  'status',
  'overview',
  'council',
  'quests',
  'shop',
  'treasure',
  'scripture',
  'forge',
  'alchemy',
  'talisman',
  'formation',
  'mine',
  'herbs',
  'lamps',
  'exchange',
])

const route = useRoute()
const router = useRouter()
const characterStore = useCharacterStore()
const sectStore = useSectStore()

const loadError = ref('')
const logEntries = ref<GameLogEntry[]>([])

const mode = computed<SectMode>(() => {
  const m = route.query.mode
  if (typeof m === 'string' && MODE_SET.has(m)) {
    return m as SectMode
  }
  return sectStore.inSect ? 'overview' : 'join'
})

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logEntries.value = [...logEntries.value.slice(-49), createLogEntry(message, level)]
}

function setMode(next: SectMode): void {
  void router.replace({ query: { ...route.query, mode: next } })
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
  sectStore.applyMeFromCharacter()
  const err = await sectStore.refresh()
  if (err) {
    loadError.value = err
    pushLog(err, 'warning')
  } else {
    pushLog('宗门页已就绪：等级/人事/设施权威在服务端。', 'info')
  }
  if (!MODE_SET.has(String(route.query.mode ?? ''))) {
    const def: SectMode = sectStore.inSect ? 'overview' : 'join'
    void router.replace({ query: { ...route.query, mode: def } })
  }
})

watch(
  () => characterStore.character?.sect,
  () => {
    sectStore.applyMeFromCharacter()
  },
)

function onJoined(): void {
  pushLog(sectStore.lastMessage || '入宗成功', 'success')
  setMode('overview')
}
</script>

<template>
  <div class="sect-page">
    <AuthSessionBar />

    <div class="page-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-text tag="b" size="large">宗门</el-text>
      <el-text type="info" size="small">M7-V+ · 等级 / 人事 / 十设施</el-text>
      <div class="mode-nav">
        <el-button size="small" :type="mode === 'join' ? 'primary' : 'default'" @click="setMode('join')">
          拜入/建宗
        </el-button>
        <el-button
          size="small"
          :type="mode === 'overview' ? 'primary' : 'default'"
          :disabled="!sectStore.inSect"
          @click="setMode('overview')"
        >
          总览
        </el-button>
        <el-button
          size="small"
          :type="mode === 'council' ? 'primary' : 'default'"
          :disabled="!sectStore.inSect"
          @click="setMode('council')"
        >
          议事厅
        </el-button>
        <el-button
          size="small"
          :type="mode === 'quests' ? 'primary' : 'default'"
          :disabled="!sectStore.inSect"
          @click="setMode('quests')"
        >
          任务殿
        </el-button>
        <el-button
          size="small"
          :type="mode === 'treasure' ? 'primary' : 'default'"
          :disabled="!sectStore.inSect"
          @click="setMode('treasure')"
        >
          藏宝阁
        </el-button>
        <el-button
          size="small"
          :type="mode === 'scripture' ? 'primary' : 'default'"
          :disabled="!sectStore.inSect"
          @click="setMode('scripture')"
        >
          藏经阁
        </el-button>
        <el-button
          size="small"
          :type="mode === 'forge' ? 'primary' : 'default'"
          :disabled="!sectStore.inSect"
          @click="setMode('forge')"
        >
          锻造工坊
        </el-button>
        <el-button
          size="small"
          :type="mode === 'alchemy' ? 'primary' : 'default'"
          :disabled="!sectStore.inSect"
          @click="setMode('alchemy')"
        >
          炼丹阁
        </el-button>
        <el-button
          size="small"
          :type="mode === 'talisman' ? 'primary' : 'default'"
          :disabled="!sectStore.inSect"
          @click="setMode('talisman')"
        >
          服务工坊
        </el-button>
        <el-button
          size="small"
          :type="mode === 'formation' ? 'primary' : 'default'"
          :disabled="!sectStore.inSect"
          @click="setMode('formation')"
        >
          大阵
        </el-button>
        <el-button
          size="small"
          :type="mode === 'mine' ? 'primary' : 'default'"
          :disabled="!sectStore.inSect"
          @click="setMode('mine')"
        >
          矿脉
        </el-button>
        <el-button
          size="small"
          :type="mode === 'herbs' ? 'primary' : 'default'"
          :disabled="!sectStore.inSect"
          @click="setMode('herbs')"
        >
          灵药园
        </el-button>
        <el-button
          size="small"
          :type="mode === 'shop' ? 'primary' : 'default'"
          :disabled="!sectStore.inSect"
          @click="setMode('shop')"
        >
          商店
        </el-button>
        <el-button size="small" :type="mode === 'lamps' ? 'primary' : 'default'" @click="setMode('lamps')">
          魂灯
        </el-button>
        <el-button
          size="small"
          :type="mode === 'exchange' ? 'primary' : 'default'"
          @click="setMode('exchange')"
        >
          兑宠
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

    <SectStatusPanel :sect="sectStore.me" />

    <div class="main-grid">
      <div class="main-left">
        <SectJoinCreatePanel v-if="mode === 'join'" @log="pushLog" @joined="onJoined" />
        <SectOverviewPanel v-else-if="mode === 'overview' || mode === 'status'" @log="pushLog" />
        <SectCouncilPanel v-else-if="mode === 'council'" @log="pushLog" />
        <SectQuestPanel v-else-if="mode === 'quests'" @log="pushLog" />
        <SectTreasuryPanel v-else-if="mode === 'treasure'" @log="pushLog" />
        <SectScripturePanel v-else-if="mode === 'scripture'" @log="pushLog" />
        <SectWorkshopPanel v-else-if="mode === 'forge'" branch="smithing" @log="pushLog" />
        <SectWorkshopPanel v-else-if="mode === 'alchemy'" branch="alchemy" @log="pushLog" />
        <SectWorkshopPanel v-else-if="mode === 'talisman'" branch="talisman" @log="pushLog" />
        <SectFormationPanel v-else-if="mode === 'formation'" @log="pushLog" />
        <SectMinePanel v-else-if="mode === 'mine'" @log="pushLog" />
        <SectHerbPanel v-else-if="mode === 'herbs'" @log="pushLog" />
        <SectShopPanel v-else-if="mode === 'shop'" @log="pushLog" />
        <template v-else-if="mode === 'lamps'">
          <el-empty
            v-if="!sectStore.inSect"
            description="入宗后可查看同门魂灯状态"
            :image-size="64"
          />
          <SectSoulLampPanel v-else @log="pushLog" />
        </template>
        <SectPetExchangePanel v-else-if="mode === 'exchange'" @log="pushLog" />
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
.sect-page {
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
.log-line {
  padding: 0.15rem 0;
}
@media (max-width: 800px) {
  .main-grid {
    grid-template-columns: 1fr;
  }
}
</style>
