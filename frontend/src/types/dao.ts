/**
 * M6 大道领域类型（对齐设计 §7 / CharacterPublic.dao）。
 *
 * 权威字段一律来自服务端；前端禁止本地抽道或改等级。
 */

/** 角色嵌入的大道资源摘要 */
export interface DaoPublic {
  /** 本命道 id；未开道为 null */
  fate_dao_id: string | null
  /** 本命道中文名（优先展示） */
  fate_dao_label: string | null
  /** 当前道值 */
  qi: number
  /** 本周目道等级 */
  level: number
  /** 当前等级内经验 */
  exp: number
  /** 升至下一级所需经验（可选） */
  exp_to_next?: number
  /** 道池已收藏数量 */
  pool_count: number
  /** 是否可发起开道（真仙且未锁定） */
  can_open: boolean
  /** 本周目本命道是否已锁定 */
  locked: boolean
}

/** 图鉴 / 开道选项条目 */
export interface DaoCatalogEntry {
  /** 道定义 id */
  dao_id: string
  /** 中文名（服务端权威） */
  label: string
  /** 大类中文，如「元素」 */
  category_label: string
  /** 稀有度中文 */
  rarity_label: string
  /** 是否已在道池 */
  owned: boolean
  /** 简述（可选） */
  description?: string
}

/** POST /dao/open/roll 冻结的三选项会话 */
export interface DaoOpenOffer {
  /** 开道会话 id，choose 时回传 */
  session_id: string
  /** 恰好 3 张候选（服务端权威） */
  options: DaoCatalogEntry[]
  /** 是否允许从道池自选（再开 / 特殊规则） */
  allow_pool_pick: boolean
}

/** 道池条目（与图鉴字段对齐，可带获得时间） */
export interface DaoPoolEntry extends DaoCatalogEntry {
  /** 首次入池时间 ISO（可选） */
  acquired_at?: string
}

/** GET /dao/catalog 载荷 */
export interface DaoCatalogPayload {
  entries: DaoCatalogEntry[]
  /** 样本总数说明（可选） */
  sample_note?: string
}

/** GET /dao/pool 载荷 */
export interface DaoPoolPayload {
  entries: DaoPoolEntry[]
  count: number
}

/** POST /dao/open/choose 成功载荷 */
export interface DaoChooseResult {
  dao?: DaoPublic
  character?: import('./character').CharacterPublic
  message?: string
  /** 选定的本命道 id */
  fate_dao_id?: string
  fate_dao_label?: string
}

/** 战斗 / 工坊运用预览 */
export interface DaoUsagePreview {
  /** 预计消耗道值 */
  qi_cost: number
  /** 中文效果说明（来自服务端） */
  effect_label?: string
  /** 是否可运用 */
  can_use: boolean
  /** 不可用原因中文 */
  reason?: string
  /** 战斗：预计伤害/减伤倍率文案 */
  battle_hint?: string
  /** 工坊：失败率/词条文案 */
  craft_hint?: string
}

/** 运用场景 */
export type DaoUsageContext = 'battle' | 'craft'
