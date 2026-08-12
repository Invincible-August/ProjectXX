<script setup lang="ts">
/**
 * 双修页（M7 L7 · /dual-cultivation）：会话 + 四榜。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import { useCharacterStore } from '../stores/character'
import { useDualCultivationStore } from '../stores/dualCultivation'
import type { DualGender } from '../types/dualCultivation'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'

type DualMode = 'session' | 'ranks'

const route = useRoute()
const router = useRouter()
const characterStore = useCharacterStore()
const dualStore = useDualCultivationStore()

const logEntries = ref<GameLogEntry[]>([])
const busy = ref(false)
const targetName = ref('')
const techniqueId = ref('')
const genderPick = ref<DualGender>('male')
const activeBoard = ref('male_number_one')

const mode = computed<DualMode>(() =>
  route.query.mode === 'ranks' ? 'ranks' : 'session',
)

const boardKeys = computed(() =>
  dualStore.ranks ? Object.keys(dualStore.ranks.boards) : [],
)

const currentBoard = computed(() => {
  if (!dualStore.ranks) return null
  return dualStore.ranks.boards[activeBoard.value] || null
})

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logEntries.value = [...logEntries.value.slice(-49), createLogEntry(message, level)]
}

function setMode(next: DualMode): void {
  void router.replace({ query: { ...route.query, mode: next } })
}

async function run(fn: () => Promise<string | null>, okHint?: string): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await fn()
    if (err) {
      ElMessage.error(err)
      pushLog(err, 'warning')
      return
    }
    ElMessage.success(okHint || dualStore.lastMessage || '完成')
    pushLog(dualStore.lastMessage || okHint || '完成', 'success')
  } finally {
    busy.value = false
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
  await dualStore.refreshMe()
  if (dualStore.techniques.length && !techniqueId.value) {
    techniqueId.value = dualStore.techniques[0].technique_id
  }
  await dualStore.loadRanks()
  if (boardKeys.value.length) {
    activeBoard.value = boardKeys.value[0]
  }
  pushLog('双修页已就绪：会话 / 四榜。', 'info')
  if (route.query.mode !== 'session' && route.query.mode !== 'ranks') {
    void router.replace({ query: { ...route.query, mode: 'session' } })
  }
})

watch(
  () => dualStore.techniques,
  (list) => {
    if (list.length && !techniqueId.value) {
      techniqueId.value = list[0].technique_id
    }
  },
)
</script>

<template>
  <div class="dual-page">
    <AuthSessionBar />

    <div class="page-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-text tag="b" size="large">双修</el-text>
      <el-text type="info" size="small">M7 L7 · 会话 / 四榜</el-text>
      <div class="mode-nav">
        <el-button
          size="small"
          :type="mode === 'session' ? 'primary' : 'default'"
          @click="setMode('session')"
        >
          会话
        </el-button>
        <el-button
          size="small"
          :type="mode === 'ranks' ? 'primary' : 'default'"
          @click="setMode('ranks')"
        >
          四榜
        </el-button>
      </div>
    </div>

    <div class="main-grid">
      <div class="main-left">
        <el-card v-if="dualStore.me?.needs_gender" shadow="never">
          <template #header>
            <el-text tag="b">补全道途阴阳</el-text>
          </template>
          <el-text size="small" type="info" class="hint">
            进双修与上榜前须选定性别；选定后不可自行更改。
          </el-text>
          <el-radio-group v-model="genderPick" size="small">
            <el-radio-button value="male">乾道（男）</el-radio-button>
            <el-radio-button value="female">坤道（女）</el-radio-button>
          </el-radio-group>
          <el-button
            type="primary"
            size="small"
            class="mt"
            :loading="busy"
            @click="run(() => dualStore.chooseGender(genderPick), '阴阳已定')"
          >
            确认
          </el-button>
        </el-card>

        <template v-else-if="mode === 'session'">
          <el-card shadow="never">
            <template #header>
              <el-text tag="b">当前阴阳</el-text>
            </template>
            <el-text>{{ dualStore.me?.gender_label_zh || '—' }}</el-text>
          </el-card>

          <el-card v-if="dualStore.session" shadow="never" class="mt">
            <template #header>
              <el-text tag="b">进行中会话</el-text>
            </template>
            <el-text>
              {{ dualStore.session.technique_label }} · {{ dualStore.session.status }}
            </el-text>
            <el-text size="small" type="info" class="hint">
              {{ dualStore.session.inviter.name }} ↔ {{ dualStore.session.invitee.name }}
            </el-text>
            <div v-if="dualStore.session.dice" class="dice-box">
              <el-text>
                掷骰：{{ dualStore.session.dice.label_zh || dualStore.session.dice.effect_tier }}
                （{{ dualStore.session.dice.roll }} · 倍率
                {{ dualStore.session.dice.yield_mult }}）
              </el-text>
            </div>
            <div class="actions">
              <el-button
                v-if="dualStore.session.status === 'inviting'"
                size="small"
                type="primary"
                :loading="busy"
                @click="run(() => dualStore.confirm(dualStore.session!.session_id))"
              >
                确认邀约
              </el-button>
              <el-button
                v-if="
                  dualStore.session.status === 'confirmed' ||
                  dualStore.session.status === 'running'
                "
                size="small"
                type="warning"
                :loading="busy"
                @click="run(() => dualStore.roll(dualStore.session!.session_id))"
              >
                掷骰
              </el-button>
              <el-button
                v-if="dualStore.session.status === 'running'"
                size="small"
                type="success"
                :loading="busy"
                @click="run(() => dualStore.settle(dualStore.session!.session_id))"
              >
                结算领取
              </el-button>
              <el-button
                size="small"
                :loading="busy"
                @click="run(() => dualStore.cancel(dualStore.session!.session_id))"
              >
                取消
              </el-button>
            </div>
          </el-card>

          <el-card v-else shadow="never" class="mt">
            <template #header>
              <el-text tag="b">发起双修</el-text>
            </template>
            <el-select v-model="techniqueId" size="small" placeholder="选择功法">
              <el-option
                v-for="t in dualStore.techniques"
                :key="t.technique_id"
                :label="`${t.label}（${t.mode === 'mutual_gain' ? '双增' : '传修为'}）`"
                :value="t.technique_id"
              />
            </el-select>
            <el-input
              v-model="targetName"
              size="small"
              class="mt"
              placeholder="对方道号"
              clearable
            />
            <el-button
              type="primary"
              size="small"
              class="mt"
              :loading="busy"
              :disabled="!techniqueId || !targetName.trim()"
              @click="run(() => dualStore.invite(techniqueId, targetName))"
            >
              发送邀约
            </el-button>
          </el-card>
        </template>

        <el-card v-else shadow="never">
          <template #header>
            <el-text tag="b">四榜</el-text>
          </template>
          <el-radio-group v-model="activeBoard" size="small" class="boards">
            <el-radio-button v-for="k in boardKeys" :key="k" :value="k">
              {{ dualStore.ranks?.boards[k]?.label_zh || k }}
            </el-radio-button>
          </el-radio-group>
          <el-text v-if="currentBoard" size="small" type="info" class="hint">
            本人：第 {{ currentBoard.my_rank ?? '—' }} 名 · 分
            {{ currentBoard.my_score }}（门槛 {{ currentBoard.min_score }}）
          </el-text>
          <el-table
            v-if="currentBoard"
            :data="currentBoard.entries"
            size="small"
            empty-text="尚无上榜"
          >
            <el-table-column prop="rank" label="名次" width="70" />
            <el-table-column prop="name" label="道号" />
            <el-table-column prop="score" label="积分" width="90" />
          </el-table>
          <el-button size="small" class="mt" @click="dualStore.loadRanks()">刷新</el-button>
        </el-card>
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
.dual-page {
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
  gap: 0.35rem;
  width: 100%;
}
.main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 220px;
  gap: 1rem;
}
.hint {
  display: block;
  margin: 0.35rem 0 0.6rem;
}
.mt {
  margin-top: 0.5rem;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.6rem;
}
.dice-box {
  margin-top: 0.5rem;
  padding: 0.4rem 0.5rem;
  background: var(--el-fill-color-light);
}
.boards {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  margin-bottom: 0.5rem;
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
