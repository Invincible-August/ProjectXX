<script setup lang="ts">
/**
 * 天道商店页（M7 L8 · /shop）：会员帽 / 货架 / 沙盒加点。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import { useCharacterStore } from '../stores/character'
import { useCommerceStore } from '../stores/commerce'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'

type ShopMode = 'member' | 'tiandao'

const route = useRoute()
const router = useRouter()
const characterStore = useCharacterStore()
const commerceStore = useCommerceStore()

const logEntries = ref<GameLogEntry[]>([])
const busy = ref(false)
const sandboxAmount = ref(500)

const mode = computed<ShopMode>(() =>
  route.query.mode === 'tiandao' ? 'tiandao' : 'member',
)

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logEntries.value = [...logEntries.value.slice(-49), createLogEntry(message, level)]
}

function setMode(next: ShopMode): void {
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
    ElMessage.success(okHint || commerceStore.lastMessage || '完成')
    pushLog(commerceStore.lastMessage || okHint || '完成', 'success')
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
  const err = await commerceStore.refresh()
  if (err) pushLog(err, 'warning')
  else pushLog('天道商店已就绪：会员 / 货架 / 沙盒。', 'info')
  if (route.query.mode !== 'member' && route.query.mode !== 'tiandao') {
    void router.replace({ query: { ...route.query, mode: 'member' } })
  }
})
</script>

<template>
  <div class="shop-page">
    <AuthSessionBar />

    <div class="page-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-text tag="b" size="large">天道商店</el-text>
      <el-text type="info" size="small">M7 L8 · 会员 / 沙盒</el-text>
      <div class="mode-nav">
        <el-button
          size="small"
          :type="mode === 'member' ? 'primary' : 'default'"
          @click="setMode('member')"
        >
          会员
        </el-button>
        <el-button
          size="small"
          :type="mode === 'tiandao' ? 'primary' : 'default'"
          @click="setMode('tiandao')"
        >
          货架
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="commerceStore.shop?.boundary_zh"
      :title="commerceStore.shop.boundary_zh"
      type="warning"
      show-icon
      :closable="false"
      class="boundary"
    />

    <div class="main-grid">
      <div class="main-left">
        <el-card shadow="never">
          <template #header>
            <el-text tag="b">当前状态</el-text>
          </template>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="会员">
              {{ commerceStore.me?.membership?.label_zh || commerceStore.me?.membership?.tier }}
            </el-descriptions-item>
            <el-descriptions-item label="挂机帽">
              {{ commerceStore.me?.membership?.idle_cap_hours ?? 12 }} 时辰
              <el-text size="small" type="info">（过期回落十二时辰）</el-text>
            </el-descriptions-item>
            <el-descriptions-item label="到期">
              {{ commerceStore.me?.membership?.expires_at || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="天道点">
              {{ commerceStore.me?.tiandao_points ?? 0 }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

        <el-card v-if="mode === 'member'" shadow="never" class="mt">
          <template #header>
            <el-text tag="b">开通会员</el-text>
          </template>
          <el-text size="small" type="info" class="hint">
            会员·一 18 时辰 / 会员·二 24 时辰；开通耗天道点。
          </el-text>
          <div class="actions">
            <el-button
              type="primary"
              size="small"
              :loading="busy"
              @click="run(() => commerceStore.openMembership('tier1'))"
            >
              开通会员·一
            </el-button>
            <el-button
              type="success"
              size="small"
              :loading="busy"
              @click="run(() => commerceStore.openMembership('tier2'))"
            >
              开通会员·二
            </el-button>
          </div>
        </el-card>

        <el-card v-else shadow="never" class="mt">
          <template #header>
            <el-text tag="b">货架</el-text>
          </template>
          <div
            v-for="item in commerceStore.shop?.items || []"
            :key="item.item_id"
            class="item-row"
          >
            <div>
              <el-text>{{ item.label_zh }}</el-text>
              <el-text size="small" type="info" class="hint">
                耗天道点 {{ item.tiandao_cost ?? 0 }}
              </el-text>
            </div>
            <el-button
              size="small"
              type="primary"
              :loading="busy"
              @click="run(() => commerceStore.buy(item.item_id))"
            >
              兑换
            </el-button>
          </div>
        </el-card>

        <el-card shadow="never" class="mt">
          <template #header>
            <el-text tag="b">沙盒加点</el-text>
          </template>
          <el-text size="small" type="info" class="hint">
            仅开发/沙盒开关开启时可用；非真支付。
          </el-text>
          <el-input-number v-model="sandboxAmount" :min="1" :max="10000" size="small" />
          <el-button
            class="mt"
            size="small"
            type="warning"
            :loading="busy"
            @click="run(() => commerceStore.sandboxGrant(sandboxAmount))"
          >
            发放天道点
          </el-button>
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
.shop-page {
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
.boundary {
  margin-bottom: 1rem;
}
.main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 220px;
  gap: 1rem;
}
.mt {
  margin-top: 0.75rem;
}
.hint {
  display: block;
  margin: 0.25rem 0 0.5rem;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}
.item-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  padding: 0.45rem 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
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
