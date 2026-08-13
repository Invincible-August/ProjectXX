/**
 * M7 L2 道友领域类型（对齐 FriendService /friends）。
 */

/** 道友 / 申请条目 */
export interface FriendItem {
  /** 友谊行主键 */
  friendship_id: number
  /** 对方角色 id */
  peer_character_id: number
  /** 对方道号 */
  peer_name: string
  /** active | pending | rejected | cancelled */
  status: string
  /** 当前角色是否为申请人 */
  is_requester: boolean
  /** 对方大境界 key */
  peer_major_realm?: string | null
  /** 对方大境界中文名 */
  peer_major_realm_name?: string | null
  /** 对方修灵池 */
  peer_cultivation_points?: number
  /** 是否在线（WS Hub 真实在线） */
  online?: boolean
  /** 化身是否可「邀请化身」（开关开 + 助战体力够 + 非忙碌） */
  assist_available?: boolean
}

/** GET /friends 载荷 */
export interface FriendListPayload {
  friends: FriendItem[]
  incoming: FriendItem[]
  outgoing: FriendItem[]
  friend_count: number
  max_friends: number
}

/** POST /friends 申请结果 */
export interface FriendApplyResult {
  message?: string
  friendship_id?: number
}

/** POST accept / reject / DELETE 结果 */
export interface FriendActionResult {
  message?: string
  friendship_id?: number
  friend_count?: number
}

/** GET/PUT /friends/privacy */
export interface FriendPrivacyPayload {
  friend_profile_visible: boolean
  snapshot_at?: string | null
  message?: string
}

/** GET /friends/profile/{id} */
export interface FriendProfileCard {
  character_id: number
  name: string
  major_realm: string
  major_realm_name?: string
  realm_stage: number
  realm_stage_label?: string
  realm_progress: number
  cultivation_required?: number | null
  cultivation_points: number
  body_temper?: Record<string, unknown> | null
  technique_summary: Array<Record<string, unknown>>
  combat_final: {
    phys_atk: number
    magic_atk: number
    hp: number
    phys_def: number
    magic_def: number
    speed: number
  }
  life?: Record<string, unknown> | null
  online: boolean
  source: 'live' | 'snapshot' | 'fallback' | string
  snapshot_at?: string | null
}
