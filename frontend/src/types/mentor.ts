/**
 * M7 L6 师徒类型（日课三选一 + 传授 + 师承单/亲传）。
 */

export interface MentorBondItem {
  bond_id: number
  status: string
  intent: string
  role: string
  is_direct?: boolean
  master_character_id: number
  master_name: string
  apprentice_character_id: number
  apprentice_name: string
  channel_ref: string | null
  room_id: string | null
  created_at?: string | null
  accepted_at?: string | null
}

export interface MentorQuestItem {
  quest_id: string
  name: string
  description: string
  progress: number
  target_count: number
  completed: boolean
  required_for_graduate: boolean
}

export interface MentorDailyState {
  day_key: string
  lesson_kind: string | null
  lesson_kind_label_zh: string | null
  lesson_done: boolean
  lesson_dao_count?: number
  lesson_craft_count?: number
  lesson_technique_count?: number
  lesson_dao_cap?: number
  lesson_craft_cap?: number
  lesson_technique_cap?: number
  can_lesson_dao?: boolean
  can_lesson_craft?: boolean
  can_lesson_technique?: boolean
  is_direct?: boolean
  teach_count: number
  teach_cap: number
  teach_done: boolean
  study_count: number
  study_cap: number
  study_done: boolean
}

export interface MentorDaoPreview {
  apprentice_need: number
  master_pool: number
  preview_amount: number
}

export interface MentorTechniqueOption {
  technique_id: string
  name: string
  track: string
  next_cost: number
  master_level?: number
}

export interface MentorRecipeOption {
  recipe_id: string
  name: string
  branch: string
  required_sessions: number
}

export interface MentorTeachingOptions {
  dao: {
    spirit: MentorDaoPreview
    body: MentorDaoPreview
  }
  craft_techniques: MentorTechniqueOption[]
  techniques: MentorTechniqueOption[]
  study_techniques: MentorTechniqueOption[]
  recipes: MentorRecipeOption[]
  master_crafting_exp: number
}

export interface MentorTransmissionItem {
  item_kind: string
  item_id: string
  name: string
  progress: number
  required_sessions: number
  status: string
}

export interface MentorLineageDisciple {
  bond_id: number
  character_id: number
  name: string
  display_name: string
  ordinal: number
  ordinal_title_zh: string
  status: string
  graduated: boolean
  is_direct: boolean
  can_clear_direct?: boolean
  can_appoint_direct?: boolean
  direct_lock_reason?: string | null
  accepted_at: string | null
}

export interface MentorLineage {
  master_character_id: number
  master_name: string
  disciples: MentorLineageDisciple[]
  direct_cap: number
  direct_count: number
  direct_cooldown_days?: number
  can_set_direct: boolean
}

export interface MentorMePayload {
  bond: MentorBondItem | null
  incoming: MentorBondItem[]
  outgoing: MentorBondItem[]
  quests: MentorQuestItem[]
  daily: MentorDailyState | null
  options: MentorTeachingOptions | null
  transmissions: MentorTransmissionItem[]
  lineage: MentorLineage | null
  channel_ref: string | null
  auto_graduate_message?: string | null
}
