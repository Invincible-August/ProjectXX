<script setup lang="ts">
/**
 * NPC 坊市：固定货架购买 + 玩家出售换灵石。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useCharacterStore } from '../../stores/character'
import { useTradeStore } from '../../stores/trade'
import type { BazaarItem } from '../../types/trade'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const tradeStore = useTradeStore()
const characterStore = useCharacterStore()
const busy = ref(false)
const loadError = ref('')
const qtyByItem = ref<Record<string, number>>({})

function qtyOf(itemId: string): number {
  return Math.max(1, Number(qtyByItem.value[itemId] || 1))
}

function setQty(itemId: string, value: number): void {
  qtyByItem.value = { ...qtyByItem.value, [itemId]: Math.max(1, Number(value) || 1) }
}

onMounted(async () => {
  loadError.value = ''
  const err = await tradeStore.refreshBazaar()
  if (err) {
    loadError.value = err
    emit('log', err, 'warning')
  } else {
    emit('log', '坊市货架已刷新', 'info')
  }
})

async function onBuy(item: BazaarItem): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await tradeStore.bazaarBuy(item.item_id, qtyOf(item.item_id))
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(tradeStore.lastMessage || '购买成功')
    emit('log', tradeStore.lastMessage || `购入 ${item.label_zh}`, 'success')
  } finally {
    busy.value = false
  }
}

async function onSell(item: BazaarItem): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await tradeStore.bazaarSell(item.item_id, qtyOf(item.item_id))
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(tradeStore.lastMessage || '出售成功')
    emit('log', tradeStore.lastMessage || `出售 ${item.label_zh}`, 'success')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="bazaar-panel">
    <el-alert
      v-if="tradeStore.bazaar?.hint_zh"
      :title="tradeStore.bazaar.hint_zh"
      type="info"
      show-icon
      :closable="false"
      class="hint"
    />
    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
      class="hint"
    />

    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <el-text tag="b">{{ tradeStore.bazaar?.label_zh || '坊市' }} · 固定货架</el-text>
          <el-text size="small" type="info">
            灵石 {{ characterStore.character?.spirit_stones ?? tradeStore.bazaar?.spirit_stones ?? '—' }}
          </el-text>
        </div>
      </template>

      <el-table
        :data="tradeStore.bazaar?.items || []"
        size="small"
        empty-text="暂无货架"
      >
        <el-table-column prop="label_zh" label="道具" min-width="120" />
        <el-table-column prop="buy_price" label="买价" width="80" />
        <el-table-column prop="sell_price" label="收购价" width="80" />
        <el-table-column prop="owned" label="持有" width="70" />
        <el-table-column label="数量" width="110">
          <template #default="{ row }">
            <el-input-number
              :model-value="qtyOf(row.item_id)"
              :min="1"
              :max="tradeStore.bazaar?.max_qty_per_deal || 99"
              size="small"
              controls-position="right"
              @update:model-value="(v) => setQty(row.item_id, Number(v))"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              type="primary"
              :loading="busy"
              :disabled="row.buy_price <= 0"
              @click="onBuy(row)"
            >
              购买
            </el-button>
            <el-button
              size="small"
              type="warning"
              :loading="busy"
              :disabled="row.sell_price <= 0 || row.owned <= 0"
              @click="onSell(row)"
            >
              出售
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card
      v-if="(tradeStore.bazaar?.inventory_sellable || []).length"
      shadow="never"
      class="mt"
    >
      <template #header>
        <el-text tag="b">可回收（持有中）</el-text>
      </template>
      <el-text size="small" type="info" class="block-hint">
        仅普通袋道具；绑定/唯一物不可售。
      </el-text>
      <div
        v-for="row in tradeStore.bazaar?.inventory_sellable || []"
        :key="`sell-${row.item_id}`"
        class="sell-row"
      >
        <div>
          <el-text>{{ row.label_zh }}</el-text>
          <el-text size="small" type="info" class="meta">
            持有 {{ row.owned }} · 回收 {{ row.sell_price }}/个
          </el-text>
        </div>
        <div class="sell-actions">
          <el-input-number
            :model-value="qtyOf(row.item_id)"
            :min="1"
            :max="Math.min(row.owned, tradeStore.bazaar?.max_qty_per_deal || 99)"
            size="small"
            controls-position="right"
            @update:model-value="(v) => setQty(row.item_id, Number(v))"
          />
          <el-button
            size="small"
            type="warning"
            :loading="busy"
            @click="onSell(row)"
          >
            出售
          </el-button>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.hint {
  margin-bottom: 0.75rem;
}
.card-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.5rem;
  align-items: baseline;
}
.mt {
  margin-top: 0.75rem;
}
.block-hint {
  display: block;
  margin-bottom: 0.5rem;
}
.sell-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.5rem;
  align-items: center;
  padding: 0.45rem 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.meta {
  display: block;
}
.sell-actions {
  display: flex;
  gap: 0.35rem;
  align-items: center;
}
</style>
