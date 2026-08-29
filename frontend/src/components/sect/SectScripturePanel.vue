<script setup lang="ts">
/** 藏经阁：目录兑换、自研学习、上缴秘籍、管理待审。 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  donateScripture,
  exchangeScripture,
  fetchDonations,
  fetchScripture,
  fetchSectMe,
  reviewDonation,
} from '../../api/sect'
import { useCharacterStore } from '../../stores/character'
import { useInventoryStore } from '../../stores/inventory'
import { rankLabelZh, TECH_MANUAL_ID } from '../../types/techniqueCraft'
import type { InventoryItem } from '../../types/inventory'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const characterStore = useCharacterStore()
const inventoryStore = useInventoryStore()

const SCRIPTURE_ADMIN_RANKS = new Set(['founder', 'leader', 'supreme_elder'])

const data = ref<Record<string, any> | null>(null)
const donations = ref<Record<string, any>[]>([])
const canReview = ref(false)
const busy = ref(false)

const myManuals = computed(() => {
  const selfId = characterStore.character?.id
  if (selfId == null) return [] as InventoryItem[]
  return inventoryStore.items.filter((row) => {
    if (row.item_id !== TECH_MANUAL_ID) return false
    const author = row.meta?.author_character_id
    return author != null && Number(author) === Number(selfId)
  })
})

function manualSubtitle(item: InventoryItem): string {
  const label = item.meta?.label_zh
  return typeof label === 'string' && label ? label : item.item_uid
}

async function reloadDonations(): Promise<void> {
  if (!canReview.value) {
    donations.value = []
    return
  }
  const env = await fetchDonations()
  if (env.code !== 0) {
    // 403 / 无权：静默隐藏，不打扰
    canReview.value = false
    donations.value = []
    return
  }
  const items = (env.data as { items?: Record<string, any>[] } | null)?.items
  donations.value = Array.isArray(items) ? items : []
}

async function reload(): Promise<void> {
  const env = await fetchScripture()
  if (env.code !== 0) {
    ElMessage.error(env.message || '加载失败')
    return
  }
  data.value = env.data || null
  await reloadDonations()
}

async function resolveReviewGate(): Promise<void> {
  const meEnv = await fetchSectMe()
  if (meEnv.code !== 0 || !meEnv.data?.sect) {
    canReview.value = false
    return
  }
  const rank = String(meEnv.data.sect.rank || meEnv.data.sect.role || '')
  canReview.value = SCRIPTURE_ADMIN_RANKS.has(rank)
}

async function onExchange(tid: string): Promise<void> {
  busy.value = true
  try {
    const env = await exchangeScripture({ technique_id: tid })
    if (env.code !== 0) {
      ElMessage.error(env.message || '兑换失败')
      emit('log', env.message || '兑换失败', 'warning')
      return
    }
    const msg = String(env.data?.message || '已兑换')
    ElMessage.success(msg)
    emit('log', msg, 'success')
    await Promise.all([reload(), inventoryStore.load(), characterStore.fetchMe()])
  } finally {
    busy.value = false
  }
}

async function onLearn(tid: string): Promise<void> {
  busy.value = true
  try {
    const env = await exchangeScripture({ technique_id: tid })
    if (env.code !== 0) {
      ElMessage.error(env.message || '学习失败')
      emit('log', env.message || '学习失败', 'warning')
      return
    }
    const msg = String(env.data?.message || '已学习')
    ElMessage.success(msg)
    emit('log', msg, 'success')
    await Promise.all([reload(), inventoryStore.load(), characterStore.fetchMe()])
  } finally {
    busy.value = false
  }
}

async function onDonate(itemUid: string): Promise<void> {
  if (!itemUid) {
    ElMessage.warning('请选择要上缴的秘籍')
    return
  }
  busy.value = true
  try {
    const env = await donateScripture({ item_uid: itemUid })
    if (env.code !== 0) {
      ElMessage.error(env.message || '上缴失败')
      emit('log', env.message || '上缴失败', 'warning')
      return
    }
    const msg = String(env.data?.message || '已提交审核')
    ElMessage.success(msg)
    emit('log', msg, 'success')
    await Promise.all([inventoryStore.load(), reload()])
  } finally {
    busy.value = false
  }
}

async function onReview(reviewId: number, approve: boolean): Promise<void> {
  busy.value = true
  try {
    const env = await reviewDonation(reviewId, { approve })
    if (env.code !== 0) {
      ElMessage.error(env.message || '审核失败')
      emit('log', env.message || '审核失败', 'warning')
      return
    }
    const msg = String(env.data?.message || (approve ? '已通过' : '已拒绝'))
    ElMessage.success(msg)
    emit('log', msg, 'success')
    // Reject returns the manual to the donor; refresh bag if reviewer is donor.
    await Promise.all([reload(), inventoryStore.load()])
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  void (async () => {
    await Promise.all([inventoryStore.load(), resolveReviewGate()])
    await reload()
  })()
})
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">藏经阁</el-text>
    </template>
    <el-text v-if="data" size="small" type="info">贡献 {{ data.contrib }}</el-text>

    <el-text tag="b" size="small" style="display: block; margin-top: 0.75rem">目录（占位兑换）</el-text>
    <div v-for="c in data?.catalog || []" :key="`cat-${c.technique_id}`" class="row">
      <el-text>
        {{ c.label_zh }} · {{ c.cost_contribution }} 贡献
        <el-tag v-if="c.owned" size="small" type="success">已收录</el-tag>
      </el-text>
      <el-button size="small" :disabled="busy" @click="onExchange(c.technique_id)">兑换</el-button>
    </div>
    <el-text v-if="!(data?.catalog || []).length" size="small" type="info" style="display: block; margin-top: 0.35rem">
      暂无目录条目
    </el-text>

    <el-text tag="b" size="small" style="display: block; margin-top: 0.75rem">已收录自研</el-text>
    <div v-for="e in data?.entries || []" :key="`ent-${e.technique_id}`" class="row">
      <el-text>
        {{ e.label_zh || e.technique_id }}
        <el-text size="small" type="info">
          · 署名 {{ e.author_character_id ?? '—' }} · {{ rankLabelZh(e.major_rank) }}阶
        </el-text>
        · {{ e.cost_contribution }} 贡献
        <el-tag v-if="e.owned" size="small" type="success">已学会</el-tag>
        <el-tag v-else-if="!e.has_snapshot" size="small" type="info">无快照</el-tag>
      </el-text>
      <el-button
        v-if="e.has_snapshot && !e.owned"
        size="small"
        type="primary"
        :disabled="busy"
        @click="onLearn(e.technique_id)"
      >
        学习
      </el-button>
    </div>
    <el-text v-if="!(data?.entries || []).length" size="small" type="info" style="display: block; margin-top: 0.35rem">
      暂无已收录自研
    </el-text>

    <el-text tag="b" size="small" style="display: block; margin-top: 0.75rem">我的可上缴秘籍</el-text>
    <div v-for="m in myManuals" :key="m.item_uid" class="row">
      <el-text>
        {{ m.name }}
        <el-text size="small" type="info"> · {{ manualSubtitle(m) }}</el-text>
      </el-text>
      <el-button size="small" :disabled="busy" @click="onDonate(m.item_uid)">上缴</el-button>
    </div>
    <el-text v-if="!myManuals.length" size="small" type="info" style="display: block; margin-top: 0.35rem">
      背包中无本人创作的功法秘籍
    </el-text>

    <template v-if="canReview">
      <el-text tag="b" size="small" style="display: block; margin-top: 0.75rem">管理待审</el-text>
      <div v-for="d in donations" :key="d.id" class="row">
        <el-text>
          #{{ d.id }} · {{ d.kind }} · {{ d.label_zh || d.origin_technique_id || '—' }}
          <el-text size="small" type="info"> · 角色 {{ d.character_id }}</el-text>
        </el-text>
        <span class="actions">
          <el-button size="small" type="success" :disabled="busy" @click="onReview(d.id, true)">
            通过
          </el-button>
          <el-button size="small" type="danger" :disabled="busy" @click="onReview(d.id, false)">
            拒绝
          </el-button>
        </span>
      </div>
      <el-text v-if="!donations.length" size="small" type="info" style="display: block; margin-top: 0.35rem">
        暂无待审上供
      </el-text>
    </template>
  </el-card>
</template>

<style scoped>
.row {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  margin-top: 0.4rem;
  align-items: center;
}
.actions {
  display: inline-flex;
  gap: 0.35rem;
  flex-shrink: 0;
}
</style>
