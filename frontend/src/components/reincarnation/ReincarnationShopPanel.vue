<script setup lang="ts">
/**
 * 轮回商店：固定货架 + 随机货架；可花费轮回点或仙缘刷新随机商品。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  buyReincarnationShopItem,
  fetchReincarnationShop,
  refreshReincarnationShop,
} from '../../api/reincarnation'
import type { ReincarnationShopCatalog, ReincarnationShopItem } from '../../types/reincarnation'
import { useCharacterStore } from '../../stores/character'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
  bought: []
}>()

const characterStore = useCharacterStore()
const catalog = ref<ReincarnationShopCatalog | null>(null)
const loading = ref(false)
const busyId = ref<string | null>(null)
const refreshing = ref(false)
const loadError = ref('')

const fixedItems = computed<ReincarnationShopItem[]>(() => {
  const c = catalog.value
  if (!c) return []
  return c.fixed_items?.length ? c.fixed_items : c.items || []
})

const randomItems = computed<ReincarnationShopItem[]>(() => catalog.value?.random_items || [])

async function reload(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    const envelope = await fetchReincarnationShop()
    if (envelope.code !== 0 || !envelope.data) {
      loadError.value = envelope.message || '加载商店失败'
      catalog.value = null
      return
    }
    catalog.value = envelope.data
  } catch (e: unknown) {
    loadError.value = e instanceof Error ? e.message : '加载商店失败'
  } finally {
    loading.value = false
  }
}

async function onBuy(
  item: ReincarnationShopItem,
  source: 'fixed' | 'random',
): Promise<void> {
  if (busyId.value) return
  try {
    await ElMessageBox.confirm(
      `花费 ${item.cost_points} 轮回点购买「${item.label}」？`,
      '轮回商店',
      { type: 'warning', confirmButtonText: '购买', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  busyId.value = `${source}:${item.id}`
  try {
    const envelope = await buyReincarnationShopItem(item.id, source)
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || '购买失败')
    }
    if (envelope.data.character) {
      characterStore.applyCharacter(envelope.data.character)
    }
    ElMessage.success(envelope.data.message || '购买成功')
    emit('log', envelope.data.message || `购买 ${item.label}`, 'success')
    emit('bought')
    await reload()
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '购买失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busyId.value = null
  }
}

async function onRefresh(currency: 'points' | 'fate_luck'): Promise<void> {
  if (refreshing.value) return
  const cost =
    currency === 'points'
      ? catalog.value?.refresh_cost_points ?? 5
      : catalog.value?.refresh_cost_fate_luck ?? 10
  const label = currency === 'points' ? `轮回点 ${cost}` : `仙缘 ${cost}`
  try {
    await ElMessageBox.confirm(`消耗 ${label} 刷新随机货架？`, '刷新随机商品', {
      type: 'warning',
      confirmButtonText: '刷新',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  refreshing.value = true
  try {
    const envelope = await refreshReincarnationShop(currency)
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || '刷新失败')
    }
    if (envelope.data.character) {
      characterStore.applyCharacter(envelope.data.character as never)
    }
    ElMessage.success(envelope.data.message || '已刷新')
    emit('log', envelope.data.message || '随机货架已刷新', 'success')
    await reload()
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '刷新失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    refreshing.value = false
  }
}

onMounted(() => {
  void reload()
})
</script>

<template>
  <el-card v-loading="loading" shadow="never" class="shop-card">
    <template #header>
      <div class="head">
        <el-text tag="b">轮回商店</el-text>
        <el-tag size="small" type="warning">
          轮回点 {{ catalog?.reincarnation_points ?? characterStore.character?.reincarnation_points ?? 0 }}
        </el-tag>
        <el-tag size="small" type="success">
          仙缘 {{ catalog?.fate_luck ?? characterStore.character?.fate_luck ?? 0 }}
        </el-tag>
        <el-button size="small" @click="reload">重载</el-button>
      </div>
    </template>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="true"
      @close="loadError = ''"
    />

    <template v-else>
      <el-text v-if="catalog?.permanent_bonus" size="small" type="info" class="bonus">
        永久加成：初始 {{ (catalog.permanent_bonus.initial_attr_bonus * 100).toFixed(1) }}%
        · 小破 {{ (catalog.permanent_bonus.minor_growth_bonus * 100).toFixed(1) }}%
        · 大破 {{ (catalog.permanent_bonus.major_growth_bonus * 100).toFixed(1) }}%
        · 突破率 +{{ (catalog.permanent_bonus.break_rate_bonus * 100).toFixed(1) }}%
      </el-text>

      <el-divider content-position="left">固定商品</el-divider>
      <el-empty v-if="!fixedItems.length" description="暂无固定商品" :image-size="40" />
      <div v-else class="shop-list">
        <div v-for="item in fixedItems" :key="'f-' + item.id" class="shop-row">
          <div class="shop-info">
            <el-text tag="b">{{ item.label }}</el-text>
            <el-text size="small" type="info">{{ item.summary }}</el-text>
          </div>
          <el-button
            type="primary"
            size="small"
            :loading="busyId === 'fixed:' + item.id"
            :disabled="(catalog?.reincarnation_points ?? 0) < item.cost_points"
            @click="onBuy(item, 'fixed')"
          >
            {{ item.cost_points }} 点
          </el-button>
        </div>
      </div>

      <el-divider content-position="left">
        随机商品
        <el-button
          link
          type="warning"
          size="small"
          :loading="refreshing"
          @click="onRefresh('points')"
        >
          刷新（{{ catalog?.refresh_cost_points ?? 5 }} 点）
        </el-button>
        <el-button
          link
          type="success"
          size="small"
          :loading="refreshing"
          @click="onRefresh('fate_luck')"
        >
          刷新（{{ catalog?.refresh_cost_fate_luck ?? 10 }} 仙缘）
        </el-button>
      </el-divider>
      <el-empty v-if="!randomItems.length" description="暂无随机商品" :image-size="40" />
      <div v-else class="shop-list">
        <div v-for="item in randomItems" :key="'r-' + item.id" class="shop-row">
          <div class="shop-info">
            <el-text tag="b">{{ item.label }}</el-text>
            <el-text size="small" type="info">{{ item.summary }}</el-text>
          </div>
          <el-button
            type="warning"
            size="small"
            :loading="busyId === 'random:' + item.id"
            :disabled="(catalog?.reincarnation_points ?? 0) < item.cost_points"
            @click="onBuy(item, 'random')"
          >
            {{ item.cost_points }} 点
          </el-button>
        </div>
      </div>
    </template>
  </el-card>
</template>

<style scoped>
.shop-card {
  margin-top: 0.25rem;
}

.head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.bonus {
  display: block;
  margin-bottom: 0.5rem;
}

.shop-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.shop-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.shop-info {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  min-width: 0;
}
</style>
