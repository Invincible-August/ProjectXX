/**
 * M7 L8 商业化 Pinia store。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  activateMembership,
  buyCommerceItem,
  fetchCommerceMe,
  fetchCommerceShop,
  sandboxGrantTiandao,
} from '../api/commerce'
import type { CommerceMePayload, CommerceShopPayload } from '../types/commerce'
import { useCharacterStore } from './character'

export const useCommerceStore = defineStore('commerce', () => {
  const me = ref<CommerceMePayload | null>(null)
  const shop = ref<CommerceShopPayload | null>(null)
  const lastMessage = ref('')
  const loading = ref(false)

  async function refresh(): Promise<string | null> {
    loading.value = true
    try {
      const [meEnv, shopEnv] = await Promise.all([fetchCommerceMe(), fetchCommerceShop()])
      if (meEnv.code !== 0 || !meEnv.data) {
        return meEnv.message || `加载会员失败（code=${meEnv.code}）`
      }
      if (shopEnv.code !== 0 || !shopEnv.data) {
        return shopEnv.message || `加载商店失败（code=${shopEnv.code}）`
      }
      me.value = meEnv.data
      shop.value = shopEnv.data
      return null
    } finally {
      loading.value = false
    }
  }

  async function openMembership(tier: string): Promise<string | null> {
    const envelope = await activateMembership(tier)
    if (envelope.code !== 0) return envelope.message || '开通失败'
    lastMessage.value = envelope.data?.message || '会员已开通'
    await refresh()
    await useCharacterStore().fetchMe()
    return null
  }

  async function buy(itemId: string): Promise<string | null> {
    const envelope = await buyCommerceItem(itemId)
    if (envelope.code !== 0) return envelope.message || '购买失败'
    lastMessage.value = envelope.data?.message || '购买成功'
    await refresh()
    await useCharacterStore().fetchMe()
    return null
  }

  async function sandboxGrant(amount: number): Promise<string | null> {
    const envelope = await sandboxGrantTiandao(amount)
    if (envelope.code !== 0) return envelope.message || '沙盒加点失败'
    lastMessage.value = envelope.data?.message || '已发放天道点'
    await refresh()
    await useCharacterStore().fetchMe()
    return null
  }

  return {
    me,
    shop,
    lastMessage,
    loading,
    refresh,
    openMembership,
    buy,
    sandboxGrant,
  }
})
