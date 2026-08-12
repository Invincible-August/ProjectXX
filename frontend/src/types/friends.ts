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
  /** 是否在线（WS / 开发假定） */
  online?: boolean
  /** 化身助战是否可邀 */
  assist_available?: boolean
}

/** GET /friends 载荷 */
export interface FriendListPayload {
  /** 已结交道友 */
  friends: FriendItem[]
  /** 待我确认的申请 */
  incoming: FriendItem[]
  /** 我发出的待确认申请 */
  outgoing: FriendItem[]
  /** 活跃道友数 */
  friend_count: number
  /** 上限（配置） */
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
