/**
 * 布阵 Pinia store（M3）：预设三槽 + 编辑草稿 + 棋盘元数据。
 *
 * draft 为未保存草稿；isDirty 时离开页面应确认。
 * 保存不会自动更新防守快照（需在 SnapshotUpdateBar 手动触发）。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  fetchBoardMetaApi,
  fetchBenchApi,
  fetchPresetsApi,
  savePresetApi,
} from '../api/formation'
import type {
  BenchUnit,
  BoardMeta,
  FormationInfo,
  FormationPreset,
  UnitPlacement,
} from '../types/formation'

/** 编辑中的草稿结构 */
interface DraftState {
  name: string
  role: string
  formation_id: string
  units: UnitPlacement[]
}

export const useFormationStore = defineStore('formation', () => {
  const boardMeta = ref<BoardMeta | null>(null)
  const presets = ref<FormationPreset[]>([])
  const formations = ref<FormationInfo[]>([])
  const bench = ref<BenchUnit[]>([])
  const maxUnits = ref(0)
  const activeSlot = ref(0)
  const loading = ref(false)
  /** 当前编辑草稿（切槽时从预设复制） */
  const draft = ref<DraftState>({
    name: '',
    role: 'attack',
    formation_id: 'none',
    units: [],
  })

  /** 当前槽已保存的预设 */
  const activePreset = computed<FormationPreset | null>(
    () => presets.value.find((p) => p.slot === activeSlot.value) ?? null,
  )

  /** 草稿相对已保存内容是否有变化 */
  const isDirty = computed(() => {
    const saved = activePreset.value
    if (!saved) return false
    return (
      JSON.stringify({
        name: saved.name,
        role: saved.role,
        formation_id: saved.formation_id,
        units: saved.units,
      }) !== JSON.stringify(draft.value)
    )
  })

  /** 当前草稿选中阵法的地形格（用于棋盘叠加显示） */
  const draftFormation = computed<FormationInfo | null>(
    () =>
      formations.value.find((f) => f.formation_id === draft.value.formation_id) ??
      null,
  )

  /**
   * 从已保存预设复制草稿（切槽 / 加载后调用）。
   */
  function resetDraftFromPreset(): void {
    const saved = activePreset.value
    if (!saved) return
    draft.value = {
      name: saved.name,
      role: saved.role,
      formation_id: saved.formation_id,
      units: saved.units.map((u) => ({ ...u })),
    }
  }

  /**
   * 单独拉 Bench（可选；预设 load 已含 bench）。
   *
   * @returns 错误消息；成功为 null
   */
  async function loadBench(): Promise<string | null> {
    const envelope = await fetchBenchApi()
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '加载棋子清单失败'
    }
    bench.value = envelope.data.bench
    return null
  }

  /**
   * 加载棋盘元数据与预设列表。
   *
   * @returns 错误消息；成功为 null
   */
  async function load(): Promise<string | null> {
    loading.value = true
    try {
      const [metaEnvelope, presetsEnvelope] = await Promise.all([
        fetchBoardMetaApi(),
        fetchPresetsApi(),
      ])
      if (metaEnvelope.code !== 0 || !metaEnvelope.data) {
        return metaEnvelope.message || '加载棋盘配置失败'
      }
      if (presetsEnvelope.code !== 0 || !presetsEnvelope.data) {
        return presetsEnvelope.message || '加载预设失败'
      }
      boardMeta.value = metaEnvelope.data
      presets.value = presetsEnvelope.data.presets
      formations.value = presetsEnvelope.data.formations
      bench.value = presetsEnvelope.data.bench
      maxUnits.value = presetsEnvelope.data.max_units
      resetDraftFromPreset()
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 切换预设槽（丢弃草稿由调用方确认后执行）。
   */
  function selectSlot(slot: number): void {
    activeSlot.value = slot
    resetDraftFromPreset()
  }

  /**
   * 在草稿中落子 / 移动棋子。
   *
   * @param unit - Bench 棋子（须带 ref_id，灵宠/化身保存校验依赖）
   * @param x - 目标格 x
   * @param y - 目标格 y
   */
  function place(
    unit: { unit_uid: string; unit_kind: string; ref_id?: number },
    x: number,
    y: number,
  ): void {
    // 同一格已有其它棋子则不落（UI 层已提示）
    if (draft.value.units.some((u) => u.x === x && u.y === y && u.unit_uid !== unit.unit_uid)) {
      return
    }
    const existing = draft.value.units.find((u) => u.unit_uid === unit.unit_uid)
    if (existing) {
      existing.x = x
      existing.y = y
      // 旧草稿可能缺 ref_id，移动时补齐
      if (unit.ref_id != null) {
        existing.ref_id = unit.ref_id
      }
    } else {
      const placement: UnitPlacement = {
        unit_uid: unit.unit_uid,
        unit_kind: unit.unit_kind,
        x,
        y,
      }
      if (unit.ref_id != null) {
        placement.ref_id = unit.ref_id
      }
      draft.value.units.push(placement)
    }
  }

  /** 从草稿移除一个棋子。 */
  function remove(unitUid: string): void {
    draft.value.units = draft.value.units.filter((u) => u.unit_uid !== unitUid)
  }

  /**
   * 保存当前草稿到服务端。
   *
   * @returns 错误消息；成功为 null
   */
  async function save(): Promise<string | null> {
    const envelope = await savePresetApi(activeSlot.value, {
      name: draft.value.name,
      role: draft.value.role,
      formation_id: draft.value.formation_id,
      units: draft.value.units,
    })
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || `保存失败（code=${envelope.code}）`
    }
    // 覆盖本地已保存态
    const index = presets.value.findIndex((p) => p.slot === envelope.data!.slot)
    if (index >= 0) {
      presets.value[index] = envelope.data
    }
    resetDraftFromPreset()
    return null
  }

  return {
    boardMeta,
    presets,
    formations,
    bench,
    maxUnits,
    activeSlot,
    loading,
    draft,
    activePreset,
    draftFormation,
    isDirty,
    load,
    loadBench,
    selectSlot,
    place,
    remove,
    save,
  }
})
