<script setup lang="ts">
/**
 * 社交页引渡救援：普渡众生 / 同门引渡 / 亲友引渡三类名单。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useFerryStore } from '../../stores/ferry'
import type { FerryRescueCategory, FerryRescueTarget } from '../../types/ferry'
import { ferryRemainMs, formatFerryCountdown } from '../../utils/ferryCountdown'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const ferryStore = useFerryStore()
const busyId = ref<number | null>(null)
const category = ref<FerryRescueCategory>('universal')
const nowMs = ref(Date.now())
let tickTimer: ReturnType<typeof setInterval> | null = null

const costHint = computed(() => {
  const sr = ferryStore.socialRescueCosts
  if (!sr) return '救援者支付灵石；成本低于对方自救。'
  const kin = sr.kin_cost ?? sr.friend_cost
  return (
    `普渡 ${sr.friend_cost} · 亲友 ${kin} · 同门 ${sr.sect_cost} · 自救 ${sr.self_rescue_cost} 灵石`
  )
})

const categoryHint = computed(() => {
  if (category.value === 'sect') return '列出同宗且待引渡的同门（须境界更高方可救）。'
  if (category.value === 'kin') return '列出待引渡的道友、道侣、师徒与炉鼎。'
  return '列出待引渡的道友（普渡众生）。'
})

const emptyText = computed(() => {
  if (category.value === 'sect') return '暂无需要引渡的同门'
  if (category.value === 'kin') return '暂无需要引渡的亲友'
  return '暂无需要引渡的道友'
})

async function refreshList(): Promise<void> {
  const err = await ferryStore.loadRescueTargets(category.value)
  if (err) {
    emit('log', err, 'warning')
  }
}

watch(category, () => {
  void refreshList()
})

onMounted(async () => {
  const errMe = await ferryStore.loadFerry()
  if (errMe) emit('log', errMe, 'warning')
  await refreshList()
  tickTimer = setInterval(() => {
    nowMs.value = Date.now()
  }, 1000)
})

onUnmounted(() => {
  if (tickTimer) clearInterval(tickTimer)
})

function remainText(iso: string | null | undefined): string {
  if (!iso) return '—'
  const ms = ferryRemainMs(iso, nowMs.value)
  if (ms <= 0) return '即将超时'
  return formatFerryCountdown(ms)
}

async function onRescue(row: FerryRescueTarget): Promise<void> {
  if (busyId.value != null) return
  busyId.value = row.character_id
  try {
    const mode = (row.rescue_mode || 'friend') as 'friend' | 'sect' | 'kin'
    const err = await ferryStore.doSocialRescue(mode, row.name, row.character_id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(ferryStore.lastMessage || '引渡成功')
    emit('log', ferryStore.lastMessage || `已引渡「${row.name}」`, 'success')
  } finally {
    busyId.value = null
  }
}
</script>

<template>
  <el-card shadow="never" class="ferry-rescue">
    <template #header>
      <div class="hdr">
        <el-text tag="b">引渡救援</el-text>
        <el-button size="small" :loading="ferryStore.loading" @click="refreshList">
          刷新
        </el-button>
      </div>
    </template>

    <el-text size="small" type="info" class="hint">{{ costHint }}</el-text>
    <el-text size="small" class="hint">{{ categoryHint }}</el-text>

    <el-radio-group v-model="category" size="small" class="tabs">
      <el-radio-button value="universal">普渡众生</el-radio-button>
      <el-radio-button value="sect">同门引渡</el-radio-button>
      <el-radio-button value="kin">亲友引渡</el-radio-button>
    </el-radio-group>

    <el-empty
      v-if="!ferryStore.rescueTargets.length"
      :description="emptyText"
      :image-size="48"
    />
    <div v-else class="target-list">
      <div
        v-for="row in ferryStore.rescueTargets"
        :key="row.character_id"
        class="target-row"
      >
        <div class="target-main">
          <el-text tag="b">{{ row.name }}</el-text>
          <el-text size="small" type="info">
            {{ row.major_realm_name || row.major_realm || '未知境界' }}
          </el-text>
          <div class="tags">
            <el-tag
              v-for="lab in row.relation_labels_zh"
              :key="lab"
              size="small"
              type="info"
            >
              {{ lab }}
            </el-tag>
          </div>
          <el-text size="small" type="warning">
            剩余 {{ remainText(row.deadline_at) }}
          </el-text>
        </div>
        <el-button
          type="primary"
          size="small"
          :loading="busyId === row.character_id"
          @click="onRescue(row)"
        >
          引渡
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.hdr {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
}
.hint {
  display: block;
  margin-bottom: 0.4rem;
}
.tabs {
  margin: 0.35rem 0 0.75rem;
}
.target-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 420px;
  overflow: auto;
}
.target-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.55rem 0.65rem;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}
.target-main {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-width: 0;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}
</style>
