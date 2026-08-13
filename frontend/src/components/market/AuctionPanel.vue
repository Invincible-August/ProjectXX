<script setup lang="ts">
/**
 * 拍卖行：列表 + 上架 + 出价。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useTradeStore } from '../../stores/trade'
import type { AuctionLot } from '../../types/trade'
import { parseNonNegInt } from '../../utils/intMoney'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const tradeStore = useTradeStore()
const busy = ref(false)
const loadError = ref('')

const formItemId = ref('')
const formQty = ref(1)
const formStart = ref(100)
const formDuration = ref<number | undefined>(undefined)

/** 各拍品出价输入 */
const bidAmounts = ref<Record<number, number>>({})

onMounted(async () => {
  loadError.value = ''
  const err = await tradeStore.refreshAuctions()
  if (err) {
    loadError.value = err
    emit('log', err, 'warning')
  }
})

function offerSummary(lot: AuctionLot): string {
  const lines = lot.offer_items ?? []
  if (!lines.length) return '（无物品）'
  return lines.map((l) => `${l.item_id}×${l.quantity}`).join('、')
}

async function onCreate(): Promise<void> {
  if (busy.value) return
  const start = parseNonNegInt(formStart.value)
  if (start === null || start < 1) {
    ElMessage.warning('起拍灵石须为 ≥ 1 的整数')
    return
  }
  busy.value = true
  try {
    const err = await tradeStore.createLot(
      formItemId.value,
      Number(formQty.value),
      start,
      formDuration.value ?? null,
    )
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(tradeStore.lastMessage || '拍品已上架')
    emit('log', tradeStore.lastMessage || '拍卖上架成功', 'success')
    formItemId.value = ''
  } finally {
    busy.value = false
  }
}

async function onBid(lot: AuctionLot): Promise<void> {
  if (busy.value) return
  const amount = parseNonNegInt(bidAmounts.value[lot.id] ?? lot.current_price)
  if (amount === null || amount < 1) {
    ElMessage.warning('出价灵石须为 ≥ 1 的整数')
    return
  }
  busy.value = true
  try {
    const err = await tradeStore.bid(lot.id, amount)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(tradeStore.lastMessage || '出价成功')
    emit('log', tradeStore.lastMessage || `出价 #${lot.id}`, 'success')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never" class="auction-panel">
    <template #header>
      <el-text tag="b">拍卖行 · 仅灵石</el-text>
    </template>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      :closable="false"
      show-icon
      class="hint"
    />

    <div class="form-row">
      <el-input
        v-model="formItemId"
        placeholder="物品 id"
        size="small"
        clearable
        style="max-width: 140px"
      />
      <el-input-number v-model="formQty" :min="1" size="small" />
      <el-input-number
        v-model="formStart"
        :min="0"
        :step="1"
        :precision="0"
        size="small"
        :controls="false"
        placeholder="起拍"
      />
      <el-input-number
        v-model="formDuration"
        :min="60"
        size="small"
        :controls="false"
        placeholder="时长秒(可选)"
      />
      <el-button type="primary" size="small" :loading="busy" @click="onCreate">
        上架拍品
      </el-button>
    </div>

    <el-divider />

    <el-empty
      v-if="!tradeStore.auctions.length"
      description="暂无拍品"
      :image-size="48"
    />
    <div v-else class="list">
      <div v-for="lot in tradeStore.auctions" :key="lot.id" class="row">
        <div class="meta">
          <el-text tag="b">#{{ lot.id }} · {{ offerSummary(lot) }}</el-text>
          <el-text size="small" type="info">
            卖家 {{ lot.seller_name }} · 当前 {{ lot.current_price }} 灵石
            · 起拍 {{ lot.start_price }}
          </el-text>
          <el-text v-if="lot.ends_at" size="small" type="warning">
            截止 {{ lot.ends_at }}
          </el-text>
        </div>
        <div class="actions">
          <el-input-number
            v-model="bidAmounts[lot.id]"
            :min="0"
            :step="1"
            :precision="0"
            size="small"
            :controls="false"
            placeholder="出价"
          />
          <el-button
            type="primary"
            size="small"
            :loading="busy"
            @click="onBid(lot)"
          >
            出价
          </el-button>
        </div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.hint {
  margin-bottom: 0.5rem;
}

.form-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 0.75rem;
}

.meta {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  min-width: 0;
  flex: 1;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: center;
}
</style>
