<script setup lang="ts">
/**
 * 背包：普通储物袋 / 轮回袋分栏与移动。
 */
import { ElMessage } from 'element-plus'
import { useInventoryStore } from '../../stores/inventory'
import { useResearchStore } from '../../stores/research'
import type { InventoryItem } from '../../types/inventory'

const inventoryStore = useInventoryStore()

function isTechniqueManual(item: InventoryItem): boolean {
  if (item.item_type !== 'manual') return false
  if (item.item_id === 'tech_manual') return true
  return item.meta?.manual_kind === 'technique'
}

function isOccupied(item: InventoryItem): boolean {
  return Boolean(item.occupancy && item.occupancy !== 'none')
}

async function onMove(item: InventoryItem, target: 'normal' | 'reincarnation'): Promise<void> {
  const err = await inventoryStore.moveBag(item.item_uid, target)
  if (err) {
    ElMessage.error(err)
    return
  }
  ElMessage.success(target === 'reincarnation' ? '已移入轮回袋' : '已移入普通袋')
}

async function onUseManual(item: InventoryItem): Promise<void> {
  const err = await inventoryStore.use(item.item_uid)
  if (err) {
    ElMessage.error(err)
    return
  }
  ElMessage.success(`已使用${item.name}`)
  await useResearchStore().loadMine()
}
</script>

<template>
  <el-card shadow="never" v-loading="inventoryStore.loading">
    <template #header>
      <el-text tag="b">
        背包（{{ inventoryStore.items.length }}）
      </el-text>
    </template>

    <el-divider content-position="left">普通储物袋</el-divider>
    <el-empty
      v-if="inventoryStore.normalItems.length === 0"
      description="普通袋为空"
      :image-size="40"
    />
    <div v-for="item in inventoryStore.normalItems" :key="item.item_uid" class="inv-row">
      <el-text size="small">{{ item.name }}</el-text>
      <el-tag size="small" type="info">×{{ item.quantity }}</el-tag>
      <el-tag v-if="item.bag_tab_label_zh" size="small">{{ item.bag_tab_label_zh }}</el-tag>
      <el-tag v-if="item.occupancy_label_zh" size="small" type="warning">
        {{ item.occupancy_label_zh }}
      </el-tag>
      <el-button
        v-if="isTechniqueManual(item)"
        link
        type="primary"
        size="small"
        :disabled="isOccupied(item)"
        @click="onUseManual(item)"
      >
        使用
      </el-button>
      <el-button
        link
        type="warning"
        size="small"
        :disabled="isOccupied(item)"
        @click="onMove(item, 'reincarnation')"
      >
        → 轮回袋
      </el-button>
    </div>

    <el-divider content-position="left">
      轮回袋（{{ inventoryStore.reincarnationUsed }} /
      {{ inventoryStore.reincarnationCapacity }}）
    </el-divider>
    <el-text size="small" type="info" class="hint">
      轮回时普通袋清空；轮回袋内物品可带入来世，容量随轮回次数增大。
    </el-text>
    <el-empty
      v-if="inventoryStore.reincarnationItems.length === 0"
      description="轮回袋为空"
      :image-size="40"
    />
    <div v-for="item in inventoryStore.reincarnationItems" :key="item.item_uid" class="inv-row">
      <el-text size="small">{{ item.name }}</el-text>
      <el-tag size="small" type="warning">×{{ item.quantity }}</el-tag>
      <el-tag v-if="item.occupancy_label_zh" size="small" type="warning">
        {{ item.occupancy_label_zh }}
      </el-tag>
      <el-button
        link
        type="info"
        size="small"
        :disabled="item.occupancy && item.occupancy !== 'none'"
        @click="onMove(item, 'normal')"
      >
        → 普通袋
      </el-button>
    </div>
  </el-card>
</template>

<style scoped>
.inv-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}

.inv-row:last-child {
  border-bottom: none;
}

.hint {
  display: block;
  margin-bottom: 0.5rem;
}
</style>
