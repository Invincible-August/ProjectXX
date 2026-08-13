/**
 * 化身 / 神识领域类型（对齐后端 AvatarPublic + 功能解锁 / 体力 / 互传折扣）。
 */

/** 化身挂机方向（与本体 idle 方向子集一致） */
export type AvatarIdleDirection = 'none' | 'spirit' | 'body' | 'crafting'

/** 化身功能解锁条目（GET /avatar/features · me.features） */
export interface AvatarFeatureState {
  feature_id: string
  min_major: string
  label_zh: string
  summary: string
  unlocked: boolean
}

/** 下一档解锁预告 */
export interface AvatarUnlockPreview {
  next_major: string
  features: Array<{
    feature_id: string
    label_zh: string
    summary: string
    min_major: string
  }>
}

/** 化身体力面板（元婴起；未解锁为 null） */
export interface AvatarStaminaPanel {
  stamina: number
  stamina_cap: number
  daily_actions_used: number
  daily_action_cap: number
  daily_actions_remaining: number
  recovery_summary: string
  recovery_per_hour: number
}

/** 化身助战专用体力（与探索/独战体力隔离） */
export interface AvatarAssistStaminaPanel {
  assist_stamina: number
  assist_stamina_cap: number
  assist_stamina_locked: boolean
  resume_threshold: number
  battle_cost: number
  recovery_per_hour: number
  can_assist: boolean
}

/** 出战模式提示 */
export interface AvatarBattleModes {
  with_main: boolean
  solo_battle: boolean
  solo_battle_hint: string | null
}

/** 化身对外结构 GET /avatar/me */
export interface AvatarPublic {
  id: number
  name: string
  status: 'idle' | 'crafting' | 'disabled' | string
  idle_direction: AvatarIdleDirection | string
  cultivation_points: number
  body_tempering_points: number
  crafting_exp: number
  base_stats: Record<string, number>
  last_settled_at: string
  created_at: string
  features?: AvatarFeatureState[]
  unlock_preview?: AvatarUnlockPreview | null
  stamina?: AvatarStaminaPanel | null
  /** 助战专用体力（化神 friend_assist 解锁后） */
  assist_stamina?: AvatarAssistStaminaPanel | null
  battle_modes?: AvatarBattleModes
  transfer_summary?: string
  transfer_retention_ratio?: number
  /** 是否允许道友借入化身助战 */
  assist_friends_enabled?: boolean
}

/** 凝练权威闸（GET /avatar/features.condense；与 POST /condense 同源） */
export interface AvatarCondenseGate {
  can_condense: boolean
  realm_ok: boolean
  has_avatar: boolean
  stones_ok: boolean
  unlock_major_realm: string
  spirit_stone_cost: number
  block_code: number | null
  block_message: string | null
}

/** GET /avatar/features */
export interface AvatarFeaturesPayload {
  major_realm: string
  features: AvatarFeatureState[]
  unlock_preview: AvatarUnlockPreview | null
  /** 后端权威；未下发时前端应再拉 /features，勿本地猜境界 */
  condense?: AvatarCondenseGate | null
}

/** 互传预览 / 实扣审计字段 */
export interface AvatarTransferAudit {
  ok?: boolean
  gross: number
  net: number
  fee: number
  retention_ratio: number
  summary?: string
  message?: string
  direction?: string
  resource?: string
}

/** 修为互传方向 */
export type TransferDirection = 'main_to_avatar' | 'avatar_to_main'

/** GET /avatar/sense 神识读数（与 character.divine_sense 同形） */
export interface DivineSenseReading {
  capacity: number
  load: number
  soft_cap: number
  hard_cap: number
  backlash: boolean
  overload_mult?: number
  /** M4-D03：comfort / overload / critical */
  zone?: string
  backlash_tier?: string | null
  idle_mult?: number
  backlash_summary?: string | null
}

/** 角色面板神识摘要别名 */
export type DivineSenseSummary = DivineSenseReading

/** 角色面板上的化身摘要（avatar_summary） */
export interface AvatarSummary {
  id?: number
  name?: string
  status?: string
  idle_direction?: string
  cultivation_points?: number
  body_tempering_points?: number
  crafting_exp?: number
  /** 化身线程挂机锚点（片内进度条用） */
  last_settled_at?: string
}

/** 双线程挂机速率预览（dual_idle_preview；大厅修炼区完整字段） */
export interface DualIdlePreview {
  main_idle_direction?: string
  main_cultivation_per_tick?: number
  main_body_per_tick?: number
  main_crafting_per_tick?: number
  avatar_idle_direction?: string
  avatar_cultivation_per_tick?: number
  avatar_body_per_tick?: number
  avatar_crafting_per_tick?: number
  /** 化身每周天耗石（共享本体灵石池） */
  avatar_stones_per_tick?: number
  /** 化身挂机锚点 ISO；缺省时回退 avatar_summary.last_settled_at */
  avatar_last_settled_at?: string
}

/** 探索代理桩 */
export interface AvatarExploreStatus {
  unlocked: boolean
  implemented: boolean
  message: string
  region_id: string | null
  stamina: AvatarStaminaPanel | null
  action_cost: number
}
