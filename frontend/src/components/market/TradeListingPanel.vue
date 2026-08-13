<script setup lang="ts">
/**
 * 交易行一口价：列表 + 上架 + 购买/撤单。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useCharacterStore } from '../../stores/character'
import { useTradeStore } from '../../stores/trade'
import type { Listing } from '../../types/trade'
import { parseNonNegInt } from '../../utils/intMoney'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const tradeStore = useTradeStore()
const characterStore = useCharacterStore()
const busy = ref(false)
const loadError = ref('')

/** 上架表单：物品 id / 数量 / 灵石标价 */
const formItemId = ref('')
const formQty = ref(1)
const formPrice = ref(100)

const myId = computed(() => characterStore.character?.id ?? 0)

onMounted(async () => {
  loadError.value = ''
  const err = await tradeStore.refreshListings()
  if (err) {
    loadError.value = err
    emit('log', err, 'warning')
  }
})

/** 展示挂单物品摘要 */
function offerSummary(listing: Listing): string {
  const lines = listing.offer_items ?? []
  if (!lines.length) return '（无物品）'
  return lines.map((l) => `${l.item_id}×${l.quantity}`).join('、')
}

async function onCreate(): Promise<void> {
  if (busy.value) return
  const price = parseNonNegInt(formPrice.value)
  if (price === null || price < 1) {
    ElMessage.warning('灵石标价须为 ≥ 1 的整数')
    return
  }
  busy.value = true
  try {
    const err = await tradeStore.createFixedPriceListing(
      formItemId.value,
      Number(formQty.value),
      price,
    )
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(tradeStore.lastMessage || '已上架')
    emit('log', tradeStore.lastMessage || '交易行上架成功', 'success')
    formItemId.value = ''
  } finally {
    busy.value = false
  }
}

async function onBuy(listing: Listing): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await tradeStore.buy(listing.id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(tradeStore.lastMessage || '成交成功')
    emit('log', tradeStore.lastMessage || `购得 #${listing.id}`, 'success')
  } finally {
    busy.value = false
  }
}

async function onCancel(listing: Listing): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await tradeStore.cancel(listing.id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(tradeStore.lastMessage || '已撤单')
    emit('log', tradeStore.lastMessage || `撤单 #${listing.id}`, 'info')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never" class="listing-panel">
    <template #header>
      <el-text tag="b">交易行 · 一口价</el-text>
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
        style="max-width: 160px"
      />
      <el-input-number v-model="formQty" :min="1" size="small" />
      <el-input-number
        v-model="formPrice"
        :min="0"
        :step="1"
        :precision="0"
        size="small"
        :controls="false"
        placeholder="灵石"
      />
      <el-button type="primary" size="small" :loading="busy" @click="onCreate">
        上架
      </el-button>
    </div>
    <el-text size="small" type="info" class="form-hint">
      一口价：物品从背包托管；绑定物不可上架。
    </el-text>

    <el-divider />

    <el-empty
      v-if="!tradeStore.listings.length"
      description="暂无挂单"
      :image-size="48"
    />
    <div v-else class="list">
      <div v-for="item in tradeStore.listings" :key="item.id" class="row">
        <div class="meta">
          <el-text tag="b">#{{ item.id }} · {{ item.mode_label_zh }}</el-text>
          <el-text size="small">{{ offerSummary(item) }}</el-text>
          <el-text size="small" type="info">
            卖家 {{ item.seller_name }} ·
            <template v-if="item.mode === 'fixed_price'">
              {{ item.price_spirit_stones }} 灵石
            </template>
            <template v-else>易物</template>
          </el-text>
        </div>
        <div class="actions">
          <el-button
            v-if="item.seller_character_id === myId"
            size="small"
            :loading="busy"
            @click="onCancel(item)"
          >
            撤单
          </el-button>
          <el-button
            v-else
            type="primary"
            size="small"
            :loading="busy"
            @click="onBuy(item)"
          >
            购买
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

.form-hint {
  display: block;
  margin-top: 0.35rem;
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
  gap: 0.35rem;
}
</style>
