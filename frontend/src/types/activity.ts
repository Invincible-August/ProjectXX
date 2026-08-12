/**
 * 活动互斥快照（CharacterPublic.activity）。
 */

export type ActivityMode =
  | 'free'
  | 'idle'
  | 'craft'
  | 'tribulation'
  | 'awaiting_ferry'
  | 'reincarnating'
  | 'breaking_through'
  | 'secret_realm'
  | string

export interface ActivityBlockers {
  enter_idle?: string | null
  start_craft?: string | null
  start_battle?: string | null
  breakthrough?: string | null
  start_tribulation?: string | null
}

/** 服务端活动态摘要（显性展示） */
export interface ActivitySnapshot {
  mode: ActivityMode
  mode_label: string
  status: string
  idle_direction: string
  craft_running: number
  in_secret_realm?: boolean
  can_enter_idle: boolean
  can_start_craft: boolean
  can_start_battle: boolean
  can_breakthrough: boolean
  can_start_tribulation: boolean
  blockers: ActivityBlockers
}
