/**
 * M5 / M7 L6 待引渡 / 社交引渡 / 轮回 Pinia store。
 *
 * 注意：后端 `/ferry/me` 可能返回嵌套 `{ status, ferry }`，本 store 统一解包为 FerryPublic。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  enterReincarnation,
  fetchFerry,
  fetchRescueTargets,
  selfRescue,
  socialRescue,
} from '../api/ferry'
import {
  altarReincarnation,
  fetchReincarnationLogs,
  previewReincarnation,
} from '../api/reincarnation'
import type {
  FerryPublic,
  FerryRescueCategory,
  FerryRescueTarget,
  SocialRescueCosts,
} from '../types/ferry'
import type {
  ReincarnationLogItem,
  ReincarnationPath,
  ReincarnationPreview,
} from '../types/reincarnation'
import { useCharacterStore } from './character'

/** `/ferry/me` 可能的嵌套信封 */
interface FerryMeEnvelope {
  status?: string
  ferry?: FerryPublic | null
  deadline_at?: string
  can_self_rescue?: boolean
  self_rescue_cost?: number
  self_rescue_reason?: string | null
  self_rescue_cost_label?: string
  self_rescue_cost_currency?: string
  self_rescue_cooldown_seconds?: number
  self_rescue_cooldown_total_seconds?: number
  spirit_stones?: number
  social_rescue?: SocialRescueCosts
  character?: unknown
  message?: string
  forced_reincarnation?: unknown
}

/**
 * 从 `/ferry/me` data 解出 FerryPublic；非待引渡返回 null。
 *
 * @param data - API data
 */
function unwrapFerry(data: unknown): FerryPublic | null {
  if (!data || typeof data !== 'object') return null
  const raw = data as FerryMeEnvelope
  // 嵌套优先
  if (raw.ferry && typeof raw.ferry === 'object') {
    return raw.ferry as FerryPublic
  }
  // 顶层展开（后端兼容字段）
  if (typeof raw.deadline_at === 'string') {
    return {
      deadline_at: raw.deadline_at,
      can_self_rescue: Boolean(raw.can_self_rescue),
      self_rescue_cost: raw.self_rescue_cost,
      self_rescue_reason: raw.self_rescue_reason as string | null | undefined,
      self_rescue_cost_label: raw.self_rescue_cost_label as string | undefined,
      self_rescue_cost_currency: raw.self_rescue_cost_currency as string | undefined,
      self_rescue_cooldown_seconds: raw.self_rescue_cooldown_seconds as number | undefined,
      self_rescue_cooldown_total_seconds:
        raw.self_rescue_cooldown_total_seconds as number | undefined,
      spirit_stones: raw.spirit_stones as number | undefined,
      social_rescue: raw.social_rescue,
    }
  }
  return null
}

export const useFerryStore = defineStore('ferry', () => {
  const ferry = ref<FerryPublic | null>(null)
  /** 社交引渡成本（非待引渡时也可从 /ferry/me 拿到） */
  const socialRescueCosts = ref<SocialRescueCosts | null>(null)
  /** 当前类别救援名单 */
  const rescueTargets = ref<FerryRescueTarget[]>([])
  const rescueCategory = ref<FerryRescueCategory>('universal')
  const rescueCategoryLabel = ref('普渡众生')
  const preview = ref<ReincarnationPreview | null>(null)
  const logs = ref<ReincarnationLogItem[]>([])
  const loading = ref(false)
  const lastMessage = ref('')

  const deadlineAt = computed(() => ferry.value?.deadline_at ?? null)
  const canSelfRescue = computed(() => Boolean(ferry.value?.can_self_rescue))

  /**
   * 若响应带 character 则 apply；否则拉 `/me` 兜底。
   *
   * @param character - 可选角色面板
   */
  async function applyOrRefresh(character: unknown): Promise<void> {
    const store = useCharacterStore()
    if (character && typeof character === 'object' && 'id' in (character as object)) {
      store.applyCharacter(character as Parameters<typeof store.applyCharacter>[0])
      return
    }
    await store.fetchMe()
  }

  /**
   * 拉取待引渡状态（解包嵌套 ferry；超时强制轮回则刷新角色）。
   *
   * @returns 错误消息；成功为 null
   */
  async function loadFerry(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await fetchFerry()
      if (envelope.code !== 0) {
        return envelope.message || `加载引渡状态失败（code=${envelope.code}）`
      }
      const data = envelope.data as FerryMeEnvelope | FerryPublic | null
      if (
        data &&
        typeof data === 'object' &&
        'status' in data &&
        (data as FerryMeEnvelope).status === 'reincarnated'
      ) {
        const nested = data as FerryMeEnvelope
        lastMessage.value = nested.message || '引渡超时，已强制轮回'
        ferry.value = null
        await applyOrRefresh(nested.character)
        return null
      }
      ferry.value = unwrapFerry(data)
      // 顶层或嵌套 ferry 内均可带 social_rescue
      const envelopeData = data as FerryMeEnvelope | null
      socialRescueCosts.value =
        envelopeData?.social_rescue ??
        ferry.value?.social_rescue ??
        socialRescueCosts.value
      return null
    } finally {
      loading.value = false
    }
  }

  /** 自救 */
  async function doSelfRescue(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await selfRescue()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `自救失败（code=${envelope.code}）`
      }
      await applyOrRefresh(envelope.data.character)
      ferry.value = envelope.data.ferry ?? null
      lastMessage.value = envelope.data.message || '自救成功'
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 道友 / 同门 / 亲友引渡（救援者支付灵石）。
   *
   * @param mode - friend | sect | kin
   * @param targetName - 待救道号
   * @param targetCharacterId - 可选角色 id
   */
  async function doSocialRescue(
    mode: 'friend' | 'sect' | 'kin',
    targetName?: string,
    targetCharacterId?: number,
  ): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await socialRescue({
        mode,
        target_name: targetName?.trim() || null,
        target_character_id: targetCharacterId ?? null,
      })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `引渡失败（code=${envelope.code}）`
      }
      await applyOrRefresh(envelope.data.character)
      lastMessage.value = envelope.data.message || '引渡成功'
      await loadRescueTargets(rescueCategory.value)
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 按类别加载待引渡救援名单。
   *
   * @param category - universal | sect | kin
   */
  async function loadRescueTargets(
    category: FerryRescueCategory = 'universal',
  ): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await fetchRescueTargets(category)
      if (envelope.code !== 0 || !envelope.data) {
        rescueTargets.value = []
        return envelope.message || `加载救援名单失败（code=${envelope.code}）`
      }
      rescueCategory.value = (envelope.data.category as FerryRescueCategory) || category
      rescueCategoryLabel.value = envelope.data.category_label_zh || ''
      rescueTargets.value = envelope.data.items ?? []
      if (envelope.data.costs) {
        socialRescueCosts.value = envelope.data.costs
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /** 自选进入轮回（须先 preview） */
  async function enter(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await enterReincarnation({ confirm: true })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `进入轮回失败（code=${envelope.code}）`
      }
      await applyOrRefresh(envelope.data.character)
      ferry.value = null
      lastMessage.value = envelope.data.message || '轮回已结算'
      // 轮回后刷新流水
      await loadLogs()
      return null
    } finally {
      loading.value = false
    }
  }

  /** 拉取轮回预览（切换 path 时覆盖旧预览） */
  async function loadPreview(path?: ReincarnationPath): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await previewReincarnation(path ? { path } : undefined)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `预览失败（code=${envelope.code}）`
      }
      const data = envelope.data
      // 防御：后端若仍返回对象型 keep，转为文案列表
      const keep = Array.isArray(data.keep)
        ? data.keep.map(String)
        : Object.entries(data.keep as unknown as Record<string, unknown>).map(
            ([k, v]) => `${k}: ${String(v)}`,
          )
      const lose = Array.isArray(data.lose)
        ? data.lose.map(String)
        : data.lose
          ? Object.keys(data.lose as unknown as Record<string, unknown>)
          : []
      preview.value = {
        path: data.path,
        keep,
        lose,
        points_gain: Number(
          data.points_gain ?? (data as { points_estimate?: number }).points_estimate ?? 0,
        ),
        pet_carry_note: data.pet_carry_note,
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /** 主动祭坛轮回 */
  async function altar(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await altarReincarnation({ confirm: true })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `祭坛轮回失败（code=${envelope.code}）`
      }
      await applyOrRefresh(envelope.data.character)
      ferry.value = null
      lastMessage.value = envelope.data.message || '祭坛轮回完成'
      await loadLogs()
      return null
    } finally {
      loading.value = false
    }
  }

  /** 拉取流水（兼容 items / logs 两种键） */
  async function loadLogs(): Promise<string | null> {
    const envelope = await fetchReincarnationLogs()
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '加载轮回流水失败'
    }
    const payload = envelope.data as {
      items?: ReincarnationLogItem[]
      logs?: ReincarnationLogItem[]
    }
    logs.value = payload.items ?? payload.logs ?? []
    return null
  }

  function clear(): void {
    ferry.value = null
    socialRescueCosts.value = null
    rescueTargets.value = []
    preview.value = null
    logs.value = []
    lastMessage.value = ''
  }

  return {
    ferry,
    socialRescueCosts,
    rescueTargets,
    rescueCategory,
    rescueCategoryLabel,
    preview,
    logs,
    loading,
    lastMessage,
    deadlineAt,
    canSelfRescue,
    loadFerry,
    doSelfRescue,
    doSocialRescue,
    loadRescueTargets,
    enter,
    loadPreview,
    altar,
    loadLogs,
    clear,
  }
})
