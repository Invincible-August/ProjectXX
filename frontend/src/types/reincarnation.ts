/**
 * M5 轮回预览 / 祭坛 / 流水 / 新生 / 商店类型。
 */
import type { CharacterPublic } from './character'

/** 轮回路径 */
export type ReincarnationPath = 'altar' | 'voluntary_ferry' | 'forced'

/** 跨世永久加成摘要 */
export interface PermanentBonusPublic {
  initial_attr_bonus: number
  minor_growth_bonus: number
  major_growth_bonus: number
  break_rate_bonus: number
  lifetime_applied_growth: number
  constitution_slots_bought?: number
  spirit_root_slots_bought?: number
}

/** POST /reincarnation/preview */
export interface ReincarnationPreview {
  path: ReincarnationPath
  keep: string[]
  lose: string[]
  points_gain: number
  points_gain_forced?: number
  peak_major?: string
  permanent_delta?: Record<string, number>
  reincarnation_bag_slots_after?: number
  path_multiplier_key?: string
  pet_carry_note?: string
  /** 祭坛路径：是否可主动入轮回（化神期起） */
  can_altar?: boolean
  /** 不可祭坛时的中文原因 */
  altar_block_reason?: string | null
  min_major_realm?: string
  min_major_label_zh?: string
}

/** 剧情已历节点（只读） */
export interface StoryFlagsPublic {
  experienced_nodes: string[]
}

/** 轮回流水单项 */
export interface ReincarnationLogItem {
  id: number
  path: ReincarnationPath | string
  created_at: string
  points_gain?: number
  /** 后端别名 */
  points_gained?: number
  summary?: string
  from_realm_display?: string
  to_realm_display?: string
  from_major?: string
  to_major?: string
}

/** 祭坛 / 强制轮回结算响应 */
export interface ReincarnationResult {
  character: CharacterPublic
  message?: string
  points_gain?: number
  snapshot_invalidated?: boolean
  needs_newborn_setup?: boolean
  permanent_bonus?: PermanentBonusPublic
}

/** GET /reincarnation/logs */
export interface ReincarnationLogsPayload {
  items: ReincarnationLogItem[]
  /** 兼容旧键 */
  logs?: ReincarnationLogItem[]
}

/** 目录选项（灵根 / 传承 / 体质倾向） */
export interface ReincarnationCatalogOption {
  id: string
  label: string
  summary: string
}

/** 保留体质词条摘要 */
export interface KeptConstitutionItem {
  id?: number
  def_id?: string
  name?: string
  quality?: string
  kind?: string
  equipped?: boolean
}

/** GET /reincarnation/newborn */
export interface NewbornOptions {
  status: string
  name: string
  reincarnation_points: number
  reincarnation_count: number
  spirit_root_slots: number
  constitution_slots?: number
  free_spirit_root_slots: number
  extra_spirit_root_slots: number
  free_legacy_slots: number
  require_spirit_root: boolean
  spirit_roots: ReincarnationCatalogOption[]
  legacy_catalog: ReincarnationCatalogOption[]
  constitution_paths: ReincarnationCatalogOption[]
  kept_constitutions: KeptConstitutionItem[]
  permanent_bonus?: PermanentBonusPublic
  reincarnation_bag_slots?: number
  current: {
    spirit_root_tags: string[]
    legacy_items: string[]
    constitution_path?: string | null
  }
  shop_hint?: string
}

/** GET /reincarnation/shop */
export interface ReincarnationShopItem {
  id: string
  label: string
  summary: string
  cost_points: number
  effect: Record<string, number | string | Record<string, number>>
  source?: 'fixed' | 'random' | string
}

export interface ReincarnationShopCatalog {
  reincarnation_points: number
  fate_luck?: number
  items: ReincarnationShopItem[]
  fixed_items?: ReincarnationShopItem[]
  random_items?: ReincarnationShopItem[]
  refresh_cost_points?: number
  refresh_cost_fate_luck?: number
  slot_caps?: { constitution?: number; spirit_root?: number }
  permanent_bonus?: PermanentBonusPublic
  reincarnation_bag_slots?: number
}

/** POST /reincarnation/complete-newborn */
export interface CompleteNewbornRequest {
  spirit_root_ids: string[]
  legacy_ids: string[]
  constitution_path?: string | null
}
