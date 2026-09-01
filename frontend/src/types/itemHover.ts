/**
 * Fixed hover-card payload for equipment / technique / constitution / divine ability.
 * Layout is documented in 功法系统设计.md and 道具与装备实体设计.md.
 */

export interface ItemHoverElement {
  id: string
  label_zh: string
  border?: string
}

export interface ItemHoverStat {
  /** Player-visible attr name, e.g. 物理攻击 / 本源 生命 */
  label_zh: string
  /** Already signed, e.g. +12 or ×1.1 */
  value: string
}

/** Workshop product hover extras */
export interface ItemHoverInspect {
  effectTags: { id: string; label_zh: string }[]
  realmReqZh: string
}

export interface ItemHoverModel {
  name: string
  /** Top-right: source / slot / grade */
  cornerZh?: string
  /** Line under name: lv.3/lv.10 */
  subtitle?: string
  /** Craft / domain rarity id for RarityBadge (§0.0.3) */
  rarity?: string | null
  /** Optional API label_zh (粗糙…太古); color names / English ids ignored */
  rarityLabelZh?: string | null
  elements?: ItemHoverElement[]
  stats?: ItemHoverStat[]
  /** 工坊成品：功效 + 境界使用条件 */
  inspect?: ItemHoverInspect
  helpZh?: string
}

export interface PoolCandidate {
  key: string
  /** Full Chinese name for §0.0.4 name fallback */
  name?: string
  /** @deprecated Prefer name + ItemSlotVisual; kept for legacy pickers */
  shortName?: string
  worn: boolean
  hover: ItemHoverModel
  /** @deprecated Prefer rarity + rarityChipStyle */
  border?: string
  /** Craft quality / rarity id — list chips use color only */
  rarity?: string | null
  /** §0.0.4 icon key */
  icon?: string | null
}
