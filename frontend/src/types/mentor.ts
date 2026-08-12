/**
 * M7 L6 师徒类型。
 */

export interface MentorBondItem {
  bond_id: number
  status: string
  intent: string
  role: string
  master_character_id: number
  master_name: string
  apprentice_character_id: number
  apprentice_name: string
  channel_ref: string | null
  room_id: string | null
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

export interface MentorMePayload {
  bond: MentorBondItem | null
  incoming: MentorBondItem[]
  outgoing: MentorBondItem[]
  quests: MentorQuestItem[]
  channel_ref: string | null
}
