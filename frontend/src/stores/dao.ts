/**
 * M6 大道 Pinia store：me / pool / catalog / 开道会话。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  chooseDaoOpen,
  fetchDaoCatalog,
  fetchDaoMe,
  fetchDaoPool,
  previewDaoUsage,
  rollDaoOpen,
} from '../api/dao'
import type {
  DaoCatalogEntry,
  DaoOpenOffer,
  DaoPoolEntry,
  DaoPublic,
  DaoUsageContext,
  DaoUsagePreview,
} from '../types/dao'
import { useCharacterStore } from './character'

/** 道资源轮询间隔；默认 0=不轮询 */
function daoPollMs(): number {
  const raw = import.meta.env.VITE_DAO_POLL_MS
  const parsed = raw ? Number(raw) : 0
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0
}

export const useDaoStore = defineStore('dao', () => {
  const me = ref<DaoPublic | null>(null)
  const pool = ref<DaoPoolEntry[]>([])
  const catalog = ref<DaoCatalogEntry[]>([])
  /** 进行中的开道三选项 */
  const opening = ref<DaoOpenOffer | null>(null)
  const usagePreview = ref<DaoUsagePreview | null>(null)
  const loading = ref(false)
  const lastMessage = ref('')

  /** 本地偏好：战斗默认运用本命道 */
  const preferBattleUseDao = ref(
    localStorage.getItem('xiuxian.dao.prefer_battle') === '1',
  )
  /** 本地偏好：工坊默认耗道值 */
  const preferCraftUseDao = ref(
    localStorage.getItem('xiuxian.dao.prefer_craft') === '1',
  )

  let pollTimer: ReturnType<typeof setInterval> | null = null

  const hasFateDao = computed(() => Boolean(me.value?.fate_dao_id))
  const canOpen = computed(() => Boolean(me.value?.can_open))

  function setPreferBattle(v: boolean): void {
    preferBattleUseDao.value = v
    localStorage.setItem('xiuxian.dao.prefer_battle', v ? '1' : '0')
  }

  function setPreferCraft(v: boolean): void {
    preferCraftUseDao.value = v
    localStorage.setItem('xiuxian.dao.prefer_craft', v ? '1' : '0')
  }

  function applyMeFromCharacter(): void {
    const ch = useCharacterStore().character
    if (ch?.dao) {
      me.value = { ...ch.dao }
    }
  }

  /**
   * 刷新 me + pool + catalog。
   *
   * @returns 错误消息；成功为 null
   */
  async function refresh(): Promise<string | null> {
    loading.value = true
    try {
      const [meEnv, poolEnv, catalogEnv] = await Promise.all([
        fetchDaoMe(),
        fetchDaoPool(),
        fetchDaoCatalog(),
      ])
      if (meEnv.code !== 0) {
        // 后端未就绪时仍可用角色嵌入摘要
        applyMeFromCharacter()
        if (!me.value) {
          return meEnv.message || `加载大道失败（code=${meEnv.code}）`
        }
      } else if (meEnv.data) {
        me.value = meEnv.data
      }
      if (poolEnv.code === 0 && poolEnv.data) {
        pool.value = poolEnv.data.entries ?? []
      }
      if (catalogEnv.code === 0 && catalogEnv.data) {
        catalog.value = catalogEnv.data.entries ?? []
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /** 仅拉 /dao/me（轻量轮询） */
  async function refreshMe(): Promise<string | null> {
    const envelope = await fetchDaoMe()
    if (envelope.code !== 0 || !envelope.data) {
      applyMeFromCharacter()
      return envelope.message || null
    }
    me.value = envelope.data
    return null
  }

  /**
   * 开道 roll。
   *
   * @returns 错误消息；成功为 null
   */
  async function roll(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await rollDaoOpen()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `开道抽取失败（code=${envelope.code}）`
      }
      opening.value = {
        session_id: envelope.data.session_id,
        options: envelope.data.options ?? [],
        allow_pool_pick: Boolean(envelope.data.allow_pool_pick),
      }
      if (envelope.data.character) {
        useCharacterStore().applyCharacter(envelope.data.character)
      }
      lastMessage.value = envelope.data.message || '已生成三道选项'
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 选定本命道。
   *
   * @param daoId - 选项或合法池中 id
   */
  async function choose(daoId: string): Promise<string | null> {
    if (!opening.value?.session_id) {
      return '开道会话不存在，请先抽取'
    }
    loading.value = true
    try {
      const envelope = await chooseDaoOpen({
        session_id: opening.value.session_id,
        dao_id: daoId,
      })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `选定本命道失败（code=${envelope.code}）`
      }
      if (envelope.data.character) {
        useCharacterStore().applyCharacter(envelope.data.character)
      }
      if (envelope.data.dao) {
        me.value = envelope.data.dao
      } else {
        await refreshMe()
      }
      opening.value = null
      lastMessage.value =
        envelope.data.message ||
        `开道成功：${envelope.data.fate_dao_label || daoId}`
      // 刷新池
      void refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 拉取运用预览。
   *
   * @param context - battle | craft
   */
  async function loadUsagePreview(
    context: DaoUsageContext,
  ): Promise<string | null> {
    const envelope = await previewDaoUsage({ context })
    if (envelope.code !== 0 || !envelope.data) {
      usagePreview.value = null
      return envelope.message || null
    }
    usagePreview.value = envelope.data
    return null
  }

  function startPoll(): void {
    const ms = daoPollMs()
    stopPoll()
    if (ms <= 0) return
    pollTimer = setInterval(() => {
      void refreshMe()
    }, ms)
  }

  function stopPoll(): void {
    if (pollTimer !== null) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function clearOpening(): void {
    opening.value = null
  }

  return {
    me,
    pool,
    catalog,
    opening,
    usagePreview,
    loading,
    lastMessage,
    preferBattleUseDao,
    preferCraftUseDao,
    hasFateDao,
    canOpen,
    setPreferBattle,
    setPreferCraft,
    applyMeFromCharacter,
    refresh,
    refreshMe,
    roll,
    choose,
    loadUsagePreview,
    startPoll,
    stopPoll,
    clearOpening,
  }
})
