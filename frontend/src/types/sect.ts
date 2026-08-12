/**
 * M7 L1 宗门领域类型（对齐 SectService / CharacterPublic.sect）。
 *
 * 权威字段一律来自服务端；前端禁止本地改贡献或解锁功能。
 */

/** 角色嵌入 /me 的宗门摘要（散修亦有占位） */
export interface SectSummary {
  /** 是否已入宗 */
  in_sect: boolean
  /** 宗门主键；散修为 null */
  sect_id: number | null
  /** 宗门名 */
  name: string | null
  /** 职位键：member / founder 等 */
  role: string | null
  /** 职位中文 */
  role_label_zh: string | null
  /** 个人贡献点 */
  contrib: number
  /** npc | player */
  kind: string | null
  /** NPC 模板 id；自建为 null */
  template_id: string | null
  /** 箴言（可选） */
  motto?: string | null
  /** 相对散修挂机修为占位倍率 */
  idle_bonus_vs_wanderer: number
  /** 已解锁功能键列表 */
  unlocked_features: string[]
  /** 已解锁功能中文 */
  unlocked_features_zh: string[]
  /** 面板提示中文 */
  hint_zh: string
}

/** 设施闸条目 */
export interface SectFacilityGate {
  /** 是否开放 */
  enabled: boolean
  /** 关闭说明中文 */
  note: string
}

/** GET /sect/me 载荷 */
export interface SectMePayload {
  /** 宗门摘要 */
  sect: SectSummary | null
  /** 设施子闸 */
  facilities: Record<string, SectFacilityGate>
  /** 自建宗门灵石费用 */
  create_cost_spirit_stones: number
  /** 刷新后的角色面板（可选） */
  character?: import('./character').CharacterPublic
}

/** NPC 宗门目录条目 */
export interface NpcSectItem {
  /** 模板 id */
  template_id: string
  /** 中文名 */
  label_zh: string
  /** 简介 */
  summary: string
  /** 箴言 */
  motto: string
  /** 拜入最低大境界键 */
  join_min_realm: string
  /** 拜入门槛中文 */
  join_min_realm_label_zh: string
  /** 拜入灵石费用 */
  join_cost_spirit_stones: number
  /** 入宗挂机占位倍率 */
  idle_bonus_vs_wanderer: number
  /** 当前是否可拜入 */
  can_join: boolean
  /** 不可拜入原因中文 */
  block_reason_zh: string | null
}

/** GET /sect/npc 载荷 */
export interface NpcSectListPayload {
  items: NpcSectItem[]
  /** 当前是否散修 */
  wanderer: boolean
}

/** 拜入 / 自建成功载荷 */
export interface SectJoinCreateResult {
  message?: string
  sect?: SectSummary
  character?: import('./character').CharacterPublic
}

/** 宗门任务条目（含接取方维度） */
export interface SectQuestItem {
  /** 任务 id */
  quest_id: string
  /** 中文名 */
  label_zh: string
  /** 简介 */
  summary: string
  /** body | avatar */
  assignee: string
  /** 接取方中文：本体 / 化身 */
  assignee_label_zh: string
  /** 完成贡献奖励 */
  reward_contribution: number
  /** available | accepted | completed */
  status: string
  /** 是否可接 */
  can_accept: boolean
  /** 是否可交 */
  can_complete: boolean
  /** 阻断原因中文 */
  block_reason_zh: string | null
}

/** GET /sect/quests 载荷 */
export interface SectQuestListPayload {
  items: SectQuestItem[]
  /** 是否已有化身 */
  has_avatar: boolean
}

/** 接取 / 完成任务结果 */
export interface SectQuestActionResult {
  message?: string
  quest_id?: string
  assignee?: string
  reward_contribution?: number
  sect?: SectSummary
  character?: import('./character').CharacterPublic
}

/** 贡献商店条目 */
export interface SectShopItem {
  /** 商品 id */
  item_id: string
  /** 中文名 */
  label_zh: string
  /** 简介 */
  summary: string
  /** 贡献费用 */
  cost_contribution: number
  /** 兑换灵石奖励 */
  reward_spirit_stones: number
  /** 当前是否买得起 */
  can_buy: boolean
}

/** GET /sect/shop 载荷 */
export interface SectShopPayload {
  items: SectShopItem[]
  /** 当前贡献 */
  contrib: number
}

/** 商店购买结果 */
export interface SectShopBuyResult {
  message?: string
  reward_spirit_stones?: number
  sect?: SectSummary
  character?: import('./character').CharacterPublic
}

/** 魂灯条目（同门状态） */
export interface SoulLampItem {
  /** 角色 id */
  character_id: number
  /** 道号 */
  name: string
  /** 职位键 */
  role: string
  /** 职位中文 */
  role_label_zh: string
  /** 状态机键 */
  status: string
  /** 状态中文 */
  status_label_zh: string
  /** 大境界键 */
  major_realm: string
  /** 大境界中文 */
  major_realm_label_zh: string
  /** 是否待引渡 */
  awaiting_ferry: boolean
  /** 同图桩标记 */
  region_stub: string
}

/** GET /sect/soul-lamps 载荷 */
export interface SoulLampListPayload {
  items: SoulLampItem[]
  count: number
}

/** 兑宠目录条目 */
export interface ExchangeCatalogItem {
  /** 物种 id */
  species_id: string
  /** 物种中文名 */
  name: string
  /** 贡献费用 */
  cost_contribution: number
  /** 兑换品阶 */
  grade: number
  /** 是否可兑 */
  enabled: boolean
}

/** GET /sect/exchange/catalog 载荷 */
export interface ExchangeCatalogPayload {
  /** 兑宠总开关 */
  enabled: boolean
  items: ExchangeCatalogItem[]
  /** 当前贡献 */
  contrib: number
  /** 是否已入宗 */
  in_sect: boolean
}

/** 兑宠结果 */
export interface SectPetExchangeResult {
  message?: string
  pet?: unknown
  sect?: SectSummary
  character?: import('./character').CharacterPublic
}
