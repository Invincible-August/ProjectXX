/**
 * M4 背包领域类型。
 */

/** 储物袋类型 */
export type BagKind = 'normal' | 'reincarnation'

/** GET /inventory 单项 */
export interface InventoryItem {
  id: number
  item_uid: string
  item_type: string
  item_id: string
  name: string
  quantity: number
  bag_kind?: BagKind | string
  meta?: Record<string, unknown> | null
  /** 目录可交易（机缘/交易筛选） */
  tradable?: boolean
  /** 绑定物 */
  bound?: boolean
  /** 唯一物（不可发机缘） */
  unique?: boolean
  max_stack?: number
}

/** GET /inventory 分袋摘要 */
export interface InventoryBagsPayload {
  items: InventoryItem[]
  normal_items?: InventoryItem[]
  reincarnation_items?: InventoryItem[]
  reincarnation_bag_capacity?: number
  reincarnation_bag_used?: number
}
