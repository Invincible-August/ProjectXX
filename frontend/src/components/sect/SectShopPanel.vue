<script setup lang="ts">
/**
 * 宗门贡献商店面板。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useSectStore } from '../../stores/sect'
import type { SectShopItem } from '../../types/sect'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const sectStore = useSectStore()
const busy = ref(false)
const loadError = ref('')

onMounted(async () => {
  loadError.value = ''
  const err = await sectStore.loadShop()
  if (err) {
    loadError.value = err
    emit('log', err, 'warning')
  }
})

async function onBuy(item: SectShopItem): Promise<void> {
  if (busy.value || !item.can_buy) return
  busy.value = true
  try {
    const err = await sectStore.buyShop(item.item_id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(sectStore.lastMessage || `已兑换「${item.label_zh}」`)
    emit('log', sectStore.lastMessage || `商店：${item.label_zh}`, 'success')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never" class="sect-shop">
    <template #header>
      <div class="hdr">
        <el-text tag="b">贡献商店</el-text>
        <el-text size="small" type="info">当前贡献 {{ sectStore.shopContrib }}</el-text>
      </div>
    </template>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      :closable="false"
      show-icon
      class="hint"
    />

    <el-empty
      v-else-if="!sectStore.shop.length"
      description="暂无商品（未入宗或功能未解锁）"
      :image-size="48"
    />

    <div v-else class="shop-list">
      <div v-for="item in sectStore.shop" :key="item.item_id" class="shop-row">
        <div class="shop-meta">
          <el-text tag="b">{{ item.label_zh }}</el-text>
          <el-text size="small" type="info">{{ item.summary }}</el-text>
          <el-text size="small">
            费用 {{ item.cost_contribution }} 贡献
            <template v-if="item.reward_spirit_stones">
              · 得 {{ item.reward_spirit_stones }} 灵石
            </template>
          </el-text>
        </div>
        <el-button
          type="primary"
          size="small"
          :loading="busy"
          :disabled="!item.can_buy"
          @click="onBuy(item)"
        >
          兑换
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.hdr {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
}

.hint {
  margin-bottom: 0.5rem;
}

.shop-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.shop-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 0.75rem;
}

.shop-meta {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-width: 0;
  flex: 1;
}
</style>
