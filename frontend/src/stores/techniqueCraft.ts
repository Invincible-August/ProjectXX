/**
 * Technique self-research Pinia store (P1 card drafts + original cultivate).
 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  abandonTechniqueDraftApi,
  abolishTechniqueApi,
  breakthroughTechniqueApi,
  chooseTechniqueAffixApi,
  createTechniqueDraftApi,
  embedTechniqueCardApi,
  fetchTechniqueDraftsApi,
  finalizeTechniqueDraftApi,
  printTechniqueManualApi,
  rerollTechniqueAffixApi,
  rollTechniqueAffixApi,
  setTechniqueConditionsApi,
  upgradeTechniqueAffixApi,
  upgradeTechniqueBaseApi,
} from '../api/cave'
import {
  affixSlotsFromIds,
  asAffixSlots,
  type TechniqueAffixSlot,
  type TechniqueCultivatePublic,
  type TechniqueDraftPublic,
  type TechniqueMineFields,
  type TechniqueOriginalView,
} from '../types/techniqueCraft'
import { useCharacterStore } from './character'
import { useInventoryStore } from './inventory'
import { useResearchStore } from './research'

function normalizeDraft(row: TechniqueDraftPublic): TechniqueDraftPublic {
  return {
    ...row,
    elements: Array.isArray(row.elements) ? row.elements.map((x) => String(x)) : [],
    affixes: asAffixSlots(row.affixes),
    base: row.base && typeof row.base === 'object' ? row.base : {},
  }
}

function cloneOriginal(view: TechniqueOriginalView): TechniqueOriginalView {
  return {
    technique_id: view.technique_id,
    label_zh: view.label_zh,
    efficacy: view.efficacy,
    major_rank: view.major_rank,
    major_rank_label_zh: view.major_rank_label_zh ?? null,
    upgrade_points: view.upgrade_points,
    base: { ...view.base },
    affixes: view.affixes.map((slot) => ({
      ...slot,
      options: [...slot.options],
    })),
    stats: { ...view.stats },
    elements: view.elements ? [...view.elements] : undefined,
    element_limit: view.element_limit ?? null,
    weapon_limit: view.weapon_limit ?? null,
    next_rank: view.next_rank ?? null,
    next_rank_label_zh: view.next_rank_label_zh ?? null,
    breakthrough_points_required:
      view.breakthrough_points_required != null
        ? Number(view.breakthrough_points_required)
        : null,
    condition_bonus: view.condition_bonus
      ? {
          ...view.condition_bonus,
          weapon_bonus: { ...(view.condition_bonus.weapon_bonus || {}) },
          element_bonus: { ...(view.condition_bonus.element_bonus || {}) },
        }
      : undefined,
  }
}

function hasAffixPayload(affixes: TechniqueAffixSlot[] | undefined): boolean {
  return Array.isArray(affixes) && affixes.some((slot) => Boolean(slot?.chosen_id))
}

function mergeCultivate(
  prev: TechniqueOriginalView | null,
  data: TechniqueCultivatePublic,
): TechniqueOriginalView {
  const nextAffixes = asAffixSlots(data.affixes)
  const keepPrevAffixes = !hasAffixPayload(nextAffixes) && hasAffixPayload(prev?.affixes)
  const nextBase = data.base && typeof data.base === 'object' ? data.base : {}
  const keepPrevBase =
    Object.keys(nextBase).length === 0 && prev?.base && Object.keys(prev.base).length > 0
  return {
    technique_id: data.technique_id || prev?.technique_id || '',
    label_zh: prev?.label_zh || data.technique_id,
    efficacy: prev?.efficacy ?? null,
    major_rank: data.major_rank || prev?.major_rank || 'body_tempering',
    major_rank_label_zh:
      data.major_rank_label_zh !== undefined
        ? data.major_rank_label_zh
        : prev?.major_rank_label_zh ?? null,
    upgrade_points:
      data.upgrade_points != null ? Number(data.upgrade_points) : Number(prev?.upgrade_points || 0),
    base: keepPrevBase ? { ...prev!.base } : nextBase,
    affixes: keepPrevAffixes ? prev!.affixes.map((slot) => ({ ...slot, options: [...slot.options] })) : nextAffixes,
    stats:
      data.stats && typeof data.stats === 'object' && Object.keys(data.stats).length
        ? data.stats
        : prev?.stats && typeof prev.stats === 'object'
          ? { ...prev.stats }
          : {},
    elements: prev?.elements,
    element_limit: prev?.element_limit ?? null,
    weapon_limit: prev?.weapon_limit ?? null,
    next_rank: data.next_rank !== undefined ? data.next_rank : prev?.next_rank ?? null,
    next_rank_label_zh:
      data.next_rank_label_zh !== undefined
        ? data.next_rank_label_zh
        : prev?.next_rank_label_zh ?? null,
    breakthrough_points_required:
      data.breakthrough_points_required !== undefined
        ? data.breakthrough_points_required
        : prev?.breakthrough_points_required ?? null,
    condition_bonus: prev?.condition_bonus,
  }
}

export const useTechniqueCraftStore = defineStore('techniqueCraft', () => {
  const drafts = ref<TechniqueDraftPublic[]>([])
  const selectedDraftId = ref<number | null>(null)
  const selectedOriginal = ref<TechniqueOriginalView | null>(null)
  /** Last cultivate payload per technique so mine re-select does not wipe hydrate. */
  const cultivateById = ref<Record<string, TechniqueOriginalView>>({})
  const loading = ref(false)

  const selectedDraft = computed(
    () => drafts.value.find((d) => d.id === selectedDraftId.value) ?? null,
  )

  function rememberCultivate(view: TechniqueOriginalView): void {
    if (!view.technique_id) return
    cultivateById.value = {
      ...cultivateById.value,
      [view.technique_id]: cloneOriginal(view),
    }
  }

  function applyCultivate(
    prev: TechniqueOriginalView | null,
    data: TechniqueCultivatePublic,
  ): TechniqueOriginalView {
    const next = mergeCultivate(prev, data)
    rememberCultivate(next)
    return next
  }

  function applyDraft(row: TechniqueDraftPublic): void {
    const normalized = normalizeDraft(row)
    const idx = drafts.value.findIndex((d) => d.id === normalized.id)
    if (idx >= 0) {
      const next = drafts.value.slice()
      next[idx] = normalized
      drafts.value = next
    } else {
      drafts.value = [...drafts.value, normalized]
    }
    selectedDraftId.value = normalized.id
  }

  async function loadDrafts(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await fetchTechniqueDraftsApi()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '加载心法雏形失败'
      }
      drafts.value = (envelope.data.items || []).map(normalizeDraft)
      if (
        selectedDraftId.value == null ||
        !drafts.value.some((d) => d.id === selectedDraftId.value)
      ) {
        selectedDraftId.value = drafts.value[0]?.id ?? null
      }
      return null
    } finally {
      loading.value = false
    }
  }

  function selectDraft(draftId: number): void {
    selectedDraftId.value = draftId
  }

  async function createDraft(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await createTechniqueDraftApi()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '另开新篇失败'
      }
      applyDraft(envelope.data)
      return null
    } finally {
      loading.value = false
    }
  }

  async function abandonDraft(): Promise<string | null> {
    if (!selectedDraft.value) return '没有选中的心法雏形'
    const draftId = selectedDraft.value.id
    loading.value = true
    try {
      const envelope = await abandonTechniqueDraftApi(draftId)
      if (envelope.code !== 0) {
        return envelope.message || '放弃雏形失败'
      }
      drafts.value = drafts.value.filter((d) => d.id !== draftId)
      selectedDraftId.value = drafts.value[0]?.id ?? null
      return null
    } finally {
      loading.value = false
    }
  }

  async function embed(itemUid: string): Promise<{ error: string | null; failed: boolean }> {
    if (!selectedDraft.value) return { error: '没有选中的心法雏形', failed: false }
    const before = selectedDraft.value
    loading.value = true
    try {
      const envelope = await embedTechniqueCardApi(before.id, itemUid)
      if (envelope.code !== 0 || !envelope.data) {
        return { error: envelope.message || '镶嵌失败', failed: false }
      }
      applyDraft(envelope.data)
      const after = selectedDraft.value
      const failed = Boolean(
        after &&
          after.elements.length === before.elements.length &&
          (after.efficacy || null) === (before.efficacy || null),
      )
      return { error: null, failed }
    } finally {
      loading.value = false
    }
  }

  async function setConditions(
    elementLimit: string | null,
    weaponLimit: string | null,
  ): Promise<string | null> {
    if (!selectedDraft.value) return '没有选中的心法雏形'
    loading.value = true
    try {
      const envelope = await setTechniqueConditionsApi(selectedDraft.value.id, {
        element_limit: elementLimit,
        weapon_limit: weaponLimit,
      })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '确认发动条件失败'
      }
      applyDraft(envelope.data)
      return null
    } finally {
      loading.value = false
    }
  }

  async function rollAffix(slot: number): Promise<string | null> {
    if (!selectedDraft.value) return '没有选中的心法雏形'
    loading.value = true
    try {
      const envelope = await rollTechniqueAffixApi(selectedDraft.value.id, slot)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '生成词条失败'
      }
      applyDraft(envelope.data)
      return null
    } finally {
      loading.value = false
    }
  }

  async function chooseAffix(slot: number, affixId: string): Promise<string | null> {
    if (!selectedDraft.value) return '没有选中的心法雏形'
    loading.value = true
    try {
      const envelope = await chooseTechniqueAffixApi(selectedDraft.value.id, slot, affixId)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '选择词条失败'
      }
      applyDraft(envelope.data)
      return null
    } finally {
      loading.value = false
    }
  }

  async function rerollAffix(slot: number): Promise<string | null> {
    if (!selectedDraft.value) return '没有选中的心法雏形'
    loading.value = true
    try {
      const envelope = await rerollTechniqueAffixApi(selectedDraft.value.id, slot)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '重随词条失败'
      }
      applyDraft(envelope.data)
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  async function finalize(labelZh: string): Promise<string | null> {
    if (!selectedDraft.value) return '没有选中的心法雏形'
    const draft = selectedDraft.value
    loading.value = true
    try {
      const envelope = await finalizeTechniqueDraftApi(draft.id, labelZh)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '定稿失败'
      }
      drafts.value = drafts.value.filter((d) => d.id !== draft.id)
      selectedDraftId.value = drafts.value[0]?.id ?? null
      const techniqueId = envelope.data.technique_id || ''
      const priv = (envelope.data.private || {}) as TechniqueMineFields
      selectedOriginal.value = {
        technique_id: techniqueId,
        label_zh: labelZh,
        efficacy: envelope.data.efficacy || draft.efficacy,
        major_rank: priv.major_rank || envelope.data.major_rank || draft.major_rank,
        major_rank_label_zh: priv.major_rank_label_zh ?? null,
        upgrade_points: Number(priv.upgrade_points ?? envelope.data.upgrade_points ?? 0),
        base: (priv.base as Record<string, number>) || envelope.data.base || draft.base || {},
        affixes: asAffixSlots(
          priv.affixes?.length
            ? priv.affixes
            : envelope.data.affixes?.length
              ? envelope.data.affixes
              : draft.affixes,
        ),
        stats: (priv.stats as Record<string, number>) || {},
        next_rank: priv.next_rank ?? null,
        next_rank_label_zh: priv.next_rank_label_zh ?? null,
        breakthrough_points_required:
          priv.breakthrough_points_required != null
            ? Number(priv.breakthrough_points_required)
            : null,
      }
      rememberCultivate(selectedOriginal.value)
      await useResearchStore().loadMine()
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  function selectOriginalFromMine(row: TechniqueMineFields): void {
    const cached = cultivateById.value[row.id]
    const affixesFromMine =
      row.affixes && row.affixes.length
        ? asAffixSlots(row.affixes)
        : affixSlotsFromIds(row.affix_ids)
    if (cached) {
      selectedOriginal.value = {
        ...cloneOriginal(cached),
        label_zh: row.label_zh || cached.label_zh,
        efficacy: row.efficacy ?? cached.efficacy,
        major_rank: row.major_rank || cached.major_rank,
        major_rank_label_zh: row.major_rank_label_zh ?? cached.major_rank_label_zh ?? null,
        upgrade_points:
          row.upgrade_points != null ? Number(row.upgrade_points) : cached.upgrade_points,
        base:
          row.base && typeof row.base === 'object' && Object.keys(row.base).length
            ? { ...row.base }
            : { ...cached.base },
        affixes:
          row.affixes && row.affixes.length
            ? affixesFromMine
            : cached.affixes.map((slot) => ({ ...slot, options: [...slot.options] })),
        stats: row.stats && typeof row.stats === 'object' ? row.stats : { ...cached.stats },
        elements: row.elements ?? cached.elements,
        element_limit: row.element_limit ?? cached.element_limit ?? null,
        weapon_limit: row.weapon_limit ?? cached.weapon_limit ?? null,
        next_rank: row.next_rank !== undefined ? row.next_rank : cached.next_rank ?? null,
        next_rank_label_zh:
          row.next_rank_label_zh !== undefined
            ? row.next_rank_label_zh
            : cached.next_rank_label_zh ?? null,
        breakthrough_points_required:
          row.breakthrough_points_required !== undefined
            ? row.breakthrough_points_required
            : cached.breakthrough_points_required ?? null,
        condition_bonus: row.condition_bonus || cached.condition_bonus,
      }
      rememberCultivate(selectedOriginal.value)
      return
    }
    selectedOriginal.value = {
      technique_id: row.id,
      label_zh: row.label_zh,
      efficacy: row.efficacy ?? null,
      major_rank: row.major_rank || 'body_tempering',
      major_rank_label_zh: row.major_rank_label_zh ?? null,
      upgrade_points: Number(row.upgrade_points || 0),
      base: row.base && typeof row.base === 'object' ? { ...row.base } : {},
      affixes: affixesFromMine,
      stats: row.stats && typeof row.stats === 'object' ? row.stats : {},
      elements: row.elements,
      element_limit: row.element_limit ?? null,
      weapon_limit: row.weapon_limit ?? null,
      next_rank: row.next_rank ?? null,
      next_rank_label_zh: row.next_rank_label_zh ?? null,
      breakthrough_points_required:
        row.breakthrough_points_required != null
          ? Number(row.breakthrough_points_required)
          : null,
      condition_bonus: row.condition_bonus,
    }
    rememberCultivate(selectedOriginal.value)
  }

  async function upgradeBase(
    stat: 'attack' | 'defense' | 'speed',
  ): Promise<string | null> {
    if (!selectedOriginal.value) return '没有选中的原创功法'
    loading.value = true
    try {
      const envelope = await upgradeTechniqueBaseApi(selectedOriginal.value.technique_id, stat)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '基础加成失败'
      }
      selectedOriginal.value = applyCultivate(selectedOriginal.value, envelope.data)
      await useCharacterStore().fetchMe()
      await useResearchStore().loadMine()
      return null
    } finally {
      loading.value = false
    }
  }

  async function upgradeAffix(
    slot: number,
  ): Promise<{ error: string | null; failed: boolean }> {
    if (!selectedOriginal.value) return { error: '没有选中的原创功法', failed: false }
    const beforeLevel = selectedOriginal.value.affixes[slot]?.chosen_level ?? 0
    loading.value = true
    try {
      const envelope = await upgradeTechniqueAffixApi(selectedOriginal.value.technique_id, slot)
      if (envelope.code !== 0 || !envelope.data) {
        return { error: envelope.message || '词条升级失败', failed: false }
      }
      selectedOriginal.value = applyCultivate(selectedOriginal.value, envelope.data)
      await useCharacterStore().fetchMe()
      await useResearchStore().loadMine()
      const afterLevel = selectedOriginal.value.affixes[slot]?.chosen_level ?? 0
      return { error: null, failed: afterLevel === beforeLevel }
    } finally {
      loading.value = false
    }
  }

  async function breakthrough(): Promise<{ error: string | null; failed: boolean }> {
    if (!selectedOriginal.value) return { error: '没有选中的原创功法', failed: false }
    const beforeRank = selectedOriginal.value.major_rank
    loading.value = true
    try {
      const envelope = await breakthroughTechniqueApi(selectedOriginal.value.technique_id)
      if (envelope.code !== 0 || !envelope.data) {
        return { error: envelope.message || '突破失败', failed: false }
      }
      selectedOriginal.value = applyCultivate(selectedOriginal.value, envelope.data)
      await useCharacterStore().fetchMe()
      await useResearchStore().loadMine()
      return { error: null, failed: selectedOriginal.value.major_rank === beforeRank }
    } finally {
      loading.value = false
    }
  }

  async function printManual(): Promise<string | null> {
    if (!selectedOriginal.value) return '没有选中的原创功法'
    loading.value = true
    try {
      const envelope = await printTechniqueManualApi(selectedOriginal.value.technique_id)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '制成秘籍失败'
      }
      await useCharacterStore().fetchMe()
      await useInventoryStore().load()
      return null
    } finally {
      loading.value = false
    }
  }

  async function abolish(): Promise<string | null> {
    if (!selectedOriginal.value) return '没有选中的原创功法'
    loading.value = true
    try {
      const envelope = await abolishTechniqueApi(selectedOriginal.value.technique_id)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '废除失败'
      }
      selectedOriginal.value = null
      await useCharacterStore().fetchMe()
      await useResearchStore().loadMine()
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    drafts,
    selectedDraftId,
    selectedDraft,
    selectedOriginal,
    loading,
    loadDrafts,
    selectDraft,
    createDraft,
    abandonDraft,
    embed,
    setConditions,
    rollAffix,
    chooseAffix,
    rerollAffix,
    finalize,
    selectOriginalFromMine,
    upgradeBase,
    upgradeAffix,
    breakthrough,
    printManual,
    abolish,
  }
})
