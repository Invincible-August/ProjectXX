/**
 * M7 L1 宗门 Pinia store：me / npc / quests / shop / lamps / exchange。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  acceptSectQuest,
  buySectShop,
  completeSectQuest,
  createSect,
  exchangeSectPet,
  fetchExchangeCatalog,
  fetchSectMe,
  fetchSectNpc,
  fetchSectQuests,
  fetchSectShop,
  fetchSoulLamps,
  joinSect,
} from '../api/sect'
import type {
  ExchangeCatalogItem,
  ExchangeCatalogPayload,
  NpcSectItem,
  SectFacilityGate,
  SectQuestItem,
  SectShopItem,
  SectSummary,
  SoulLampItem,
} from '../types/sect'
import { useCharacterStore } from './character'

export const useSectStore = defineStore('sect', () => {
  /** 我的宗门摘要 */
  const me = ref<SectSummary | null>(null)
  /** 设施闸 */
  const facilities = ref<Record<string, SectFacilityGate>>({})
  /** 自建费用 */
  const createCostSpiritStones = ref(0)
  /** NPC 目录 */
  const npc = ref<NpcSectItem[]>([])
  /** 任务列表 */
  const quests = ref<SectQuestItem[]>([])
  /** 商店列表 */
  const shop = ref<SectShopItem[]>([])
  /** 商店侧展示用贡献 */
  const shopContrib = ref(0)
  /** 魂灯 */
  const lamps = ref<SoulLampItem[]>([])
  /** 兑宠目录 */
  const exchange = ref<ExchangeCatalogPayload | null>(null)
  const loading = ref(false)
  const lastMessage = ref('')
  const lastError = ref('')

  const inSect = computed(() => Boolean(me.value?.in_sect))
  const isWanderer = computed(() => !inSect.value)

  /**
   * 从角色嵌入摘要回填 me（后端未就绪时兜底）。
   */
  function applyMeFromCharacter(): void {
    const ch = useCharacterStore().character
    if (ch?.sect) {
      me.value = { ...ch.sect }
    }
  }

  /**
   * 应用服务端返回的 sect + character。
   *
   * @param sect - 摘要
   * @param character - 可选角色面板
   */
  function applySectResult(
    sect?: SectSummary | null,
    character?: import('../types/character').CharacterPublic,
  ): void {
    if (sect) {
      me.value = sect
    }
    if (character) {
      useCharacterStore().applyCharacter(character)
    }
  }

  /**
   * 刷新 me + NPC 目录（进页主路径）。
   *
   * @returns 错误消息；成功为 null
   */
  async function refresh(): Promise<string | null> {
    loading.value = true
    lastError.value = ''
    try {
      const [meEnv, npcEnv] = await Promise.all([fetchSectMe(), fetchSectNpc()])
      if (meEnv.code !== 0 || !meEnv.data) {
        applyMeFromCharacter()
        if (!me.value) {
          const msg = meEnv.message || `加载宗门失败（code=${meEnv.code}）`
          lastError.value = msg
          return msg
        }
      } else {
        me.value = meEnv.data.sect
        facilities.value = meEnv.data.facilities ?? {}
        createCostSpiritStones.value = Number(
          meEnv.data.create_cost_spirit_stones ?? 0,
        )
        if (meEnv.data.character) {
          useCharacterStore().applyCharacter(meEnv.data.character)
        }
      }
      if (npcEnv.code === 0 && npcEnv.data) {
        npc.value = npcEnv.data.items ?? []
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /** 仅拉 /sect/me */
  async function refreshMe(): Promise<string | null> {
    const envelope = await fetchSectMe()
    if (envelope.code !== 0 || !envelope.data) {
      applyMeFromCharacter()
      return envelope.message || null
    }
    me.value = envelope.data.sect
    facilities.value = envelope.data.facilities ?? {}
    createCostSpiritStones.value = Number(
      envelope.data.create_cost_spirit_stones ?? 0,
    )
    if (envelope.data.character) {
      useCharacterStore().applyCharacter(envelope.data.character)
    }
    return null
  }

  /** 拉取任务列表 */
  async function loadQuests(): Promise<string | null> {
    const envelope = await fetchSectQuests()
    if (envelope.code !== 0 || !envelope.data) {
      quests.value = []
      const msg = envelope.message || `加载宗门任务失败（code=${envelope.code}）`
      lastError.value = msg
      return msg
    }
    quests.value = envelope.data.items ?? []
    return null
  }

  /** 拉取贡献商店 */
  async function loadShop(): Promise<string | null> {
    const envelope = await fetchSectShop()
    if (envelope.code !== 0 || !envelope.data) {
      shop.value = []
      shopContrib.value = 0
      const msg = envelope.message || `加载宗门商店失败（code=${envelope.code}）`
      lastError.value = msg
      return msg
    }
    shop.value = envelope.data.items ?? []
    shopContrib.value = Number(envelope.data.contrib ?? 0)
    return null
  }

  /** 拉取魂灯 */
  async function loadLamps(): Promise<string | null> {
    const envelope = await fetchSoulLamps()
    if (envelope.code !== 0 || !envelope.data) {
      lamps.value = []
      const msg = envelope.message || `加载魂灯失败（code=${envelope.code}）`
      lastError.value = msg
      return msg
    }
    lamps.value = envelope.data.items ?? []
    return null
  }

  /** 拉取兑宠目录 */
  async function loadExchange(): Promise<string | null> {
    const envelope = await fetchExchangeCatalog()
    if (envelope.code !== 0 || !envelope.data) {
      exchange.value = null
      const msg = envelope.message || `加载兑宠目录失败（code=${envelope.code}）`
      lastError.value = msg
      return msg
    }
    exchange.value = envelope.data
    return null
  }

  /**
   * 拜入 NPC 宗门。
   *
   * @param templateId - NPC 模板 id
   */
  async function join(templateId: string): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await joinSect({ template_id: templateId })
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `拜入失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      applySectResult(envelope.data.sect, envelope.data.character)
      lastMessage.value = envelope.data.message || '拜入成功'
      void refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 自建宗门。
   *
   * @param name - 宗门名
   * @param motto - 箴言
   */
  async function create(
    name: string,
    motto?: string | null,
  ): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await createSect({ name, motto: motto || null })
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `建宗失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      applySectResult(envelope.data.sect, envelope.data.character)
      lastMessage.value = envelope.data.message || '建宗成功'
      void refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 接取任务。
   *
   * @param questId - 任务 id
   * @param assignee - body | avatar
   */
  async function acceptQuest(
    questId: string,
    assignee: string,
  ): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await acceptSectQuest(questId, { assignee })
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `接取失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      applySectResult(envelope.data.sect)
      lastMessage.value = envelope.data.message || '已接取任务'
      await loadQuests()
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 完成任务。
   *
   * @param questId - 任务 id
   * @param assignee - body | avatar
   */
  async function completeQuest(
    questId: string,
    assignee: string,
  ): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await completeSectQuest(questId, { assignee })
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `完成失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      applySectResult(envelope.data.sect, envelope.data.character)
      lastMessage.value = envelope.data.message || '任务完成'
      await loadQuests()
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 购买商店条目。
   *
   * @param itemId - 商品 id
   */
  async function buyShop(itemId: string): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await buySectShop({ item_id: itemId })
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `兑换失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      applySectResult(envelope.data.sect, envelope.data.character)
      lastMessage.value = envelope.data.message || '兑换成功'
      await loadShop()
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 兑宠。
   *
   * @param speciesId - 物种 id
   */
  async function exchangePet(speciesId: string): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await exchangeSectPet({ species_id: speciesId })
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `兑宠失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      applySectResult(envelope.data.sect, envelope.data.character)
      lastMessage.value = envelope.data.message || '兑宠成功'
      await loadExchange()
      return null
    } finally {
      loading.value = false
    }
  }

  /** 兑宠白名单条目便捷 getter */
  const exchangeItems = computed<ExchangeCatalogItem[]>(
    () => exchange.value?.items ?? [],
  )

  return {
    me,
    facilities,
    createCostSpiritStones,
    npc,
    quests,
    shop,
    shopContrib,
    lamps,
    exchange,
    exchangeItems,
    loading,
    lastMessage,
    lastError,
    inSect,
    isWanderer,
    applyMeFromCharacter,
    refresh,
    refreshMe,
    loadQuests,
    loadShop,
    loadLamps,
    loadExchange,
    join,
    create,
    acceptQuest,
    completeQuest,
    buyShop,
    exchangePet,
  }
})
