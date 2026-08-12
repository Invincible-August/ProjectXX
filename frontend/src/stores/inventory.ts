/**
 * M4 背包 Pinia store（普通袋 / 轮回袋）。
 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchInventory, moveInventoryBag, useItem } from '../api/inventory'
import type { BagKind, InventoryItem } from '../types/inventory'

export const useInventoryStore = defineStore('inventory', () => {
  const items = ref<InventoryItem[]>([])
  const reincarnationCapacity = ref(0)
  const reincarnationUsed = ref(0)
  const loading = ref(false)

  const normalItems = computed(() =>
    items.value.filter((x) => (x.bag_kind || 'normal') === 'normal'),
  )
  const reincarnationItems = computed(() =>
    items.value.filter((x) => x.bag_kind === 'reincarnation'),
  )

  async function load(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await fetchInventory()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '加载背包失败'
      }
      items.value = envelope.data.items || []
      reincarnationCapacity.value = envelope.data.reincarnation_bag_capacity ?? 0
      reincarnationUsed.value = envelope.data.reincarnation_bag_used ?? 0
      return null
    } finally {
      loading.value = false
    }
  }

  async function moveBag(itemUid: string, targetBag: BagKind): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await moveInventoryBag({ item_uid: itemUid, target_bag: targetBag })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '移动失败'
      }
      items.value = envelope.data.items || []
      reincarnationCapacity.value = envelope.data.reincarnation_bag_capacity ?? 0
      reincarnationUsed.value = envelope.data.reincarnation_bag_used ?? 0
      return null
    } finally {
      loading.value = false
    }
  }

  async function use(itemUid: string, quantity = 1): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await useItem({ item_uid: itemUid, quantity })
      if (envelope.code !== 0) {
        return envelope.message || '使用物品失败'
      }
      await load()
      return null
    } finally {
      loading.value = false
    }
  }

  function clear(): void {
    items.value = []
    reincarnationCapacity.value = 0
    reincarnationUsed.value = 0
  }

  return {
    items,
    normalItems,
    reincarnationItems,
    reincarnationCapacity,
    reincarnationUsed,
    loading,
    load,
    moveBag,
    use,
    clear,
  }
})
