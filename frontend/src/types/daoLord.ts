/**
 * M6 道主与赛会类型（对齐设计 §7）。
 */

/** 道主榜单座位 */
export interface DaoLordSeatPublic {
  dao_id: string
  dao_label: string
  /** 现任道主角色 id；空位无 */
  lord_character_id?: number | null
  /** 现任道主道号 */
  lord_name?: string | null
  /** 就任时间 ISO */
  claimed_at?: string | null
  /**
   * 兼容字段：空位不走手动夺位，恒为 false。
   * @deprecated 空位自动就任
   */
  can_claim: boolean
  /** 当前角色可否发起挑战 */
  can_challenge: boolean
  /** 是否虚位 */
  vacant?: boolean
  /** 是否本人任本道道主 */
  is_self_lord?: boolean
  /** 空位就任提示（非按钮语义） */
  claim_block_reason?: string | null
  /** 不可挑战原因 */
  challenge_block_reason?: string | null
  /** 冷却结束时间（可选） */
  cooldown_until?: string | null
  /** 冷却/禁用原因中文（兼容旧字段） */
  block_reason?: string | null
}

/** 空位自动就任摘要 */
export interface DaoLordAutoInaugurated {
  dao_id: string
  dao_label: string
  message?: string
  auto?: boolean
  claimed_at?: string | null
}

/** GET /dao-lord/board */
export interface DaoLordBoardPayload {
  seats: DaoLordSeatPublic[]
  updated_at?: string
  /** 本次拉取时因空位达标而自动就任 */
  auto_inaugurated?: DaoLordAutoInaugurated | null
}

/** 挑战开窗状态 */
export interface DaoLordWindowPublic {
  /** 当前是否开放 */
  open: boolean
  /** 下一开放时刻 ISO */
  next_open_at?: string | null
  /** 本窗关闭时刻 ISO */
  closes_at?: string | null
  /** 展示文案（如「每日 20:00–22:00」） */
  label: string
}

/** GET /dao-lord/windows（可多窗摘要） */
export interface DaoLordWindowsPayload {
  /** 主窗 / 当前有效窗 */
  window: DaoLordWindowPublic
  /** 额外窗列表（可选） */
  windows?: DaoLordWindowPublic[]
}

/** CharacterPublic 嵌入：自己是某道道主时 */
export interface DaoLordSummary {
  dao_id: string
  dao_label: string
  is_self: boolean
  privileges?: {
    heavenly_skill_unlocked?: boolean
    can_open_secret_realm?: boolean
    [key: string]: unknown
  } | null
}

/** 道主之争本场（M6-D06） */
export interface DaoContestPublic {
  id: number
  cycle_date: string
  status: string
  status_label: string
  force_started: boolean
  opened_at?: string | null
  registration_opens_at?: string | null
  registration_closes_at?: string | null
  fight_at?: string | null
  tz: string
  can_register: boolean
  /** 仅日程窗（不含个人资格） */
  registration_window_open?: boolean
  eta_label: string
  counts_by_dao: Array<{ dao_id: string; dao_label: string; count: number }>
  total_entrants: number
  match_count?: number
  bracket_ready?: boolean
  summary?: Record<string, unknown> | null
  p1_note?: string | null
  phase?: string | null
  phase_ends_at?: string | null
  staging_enabled?: boolean
  /** RSVP 窗口秒数（默认 60） */
  rsvp_seconds?: number
  /** RSVP 结束后首轮倒计时秒数（默认 30） */
  arena_first_round_countdown_seconds?: number
}

export interface DaoContestCurrentPayload {
  contest: DaoContestPublic
  me: {
    registered: boolean
    dao_id?: string | null
    dao_label?: string | null
    /** 个人是否具备报名资格（不含窗/已报） */
    eligible?: boolean
    eligible_block_reason?: string | null
    /** 当前可否点报名（窗内 + 资格 + 未报） */
    can_register?: boolean
    active_spectate_match_id?: number | null
    rsvp_status?: string | null
    in_arena?: boolean
    needs_rsvp?: boolean
    is_lord_rsvp?: boolean
  }
  message?: string
}

/** 擂台页载荷 */
export interface DaoContestArenaPayload {
  contest_id: number
  status: string
  phase?: string | null
  phase_ends_at?: string | null
  countdown_seconds: number
  /** 服务端当前 UTC，供客户端校准倒计时 */
  server_now?: string | null
  message_zh?: string
  action?: string
  dao_id?: string | null
  can_adjust_loadout: boolean
  in_arena: boolean
  rsvp_status?: string | null
  my_active_match?: DaoContestMatchPublic | null
  active_match_ids: number[]
  /** 本道当前整备/直播中的场次（不含其它道） */
  my_dao_active_match_ids?: number[]
  bracket: DaoContestBracketPayload
  me_character_id: number
}

/** 赛会对阵公开态 */
export interface DaoContestMatchPublic {
  id: number
  contest_id: number
  dao_id: string
  dao_label?: string
  round_kind: string
  round_kind_label?: string
  round_index: number
  bracket_slot: number
  side_a?: { character_id: number; name?: string } | null
  side_b?: { character_id: number; name?: string } | null
  winner_character_id?: number | null
  winner_name?: string | null
  status: string
  resolve_reason?: string
  result_label_zh?: string | null
  is_live_round: boolean
  live_active: boolean
  live_started_at?: string | null
  live_ends_at?: string | null
  can_replay: boolean
  can_spectate_live: boolean
  lord_defense_mode?: string | null
  lordship_transferred?: boolean
  finished_at?: string | null
  room_id?: string
}

export interface DaoContestBracketPayload {
  contest_id: number
  status: string
  dao_id?: string | null
  matches: DaoContestMatchPublic[]
  me_character_id?: number
}

export interface DaoContestMatchReportPayload {
  match: DaoContestMatchPublic
  report: {
    summary?: string
    events?: unknown[]
    live_pipeline?: Record<string, unknown>
    [key: string]: unknown
  }
  viewer_role?: 'participant' | 'spectator' | string
  /** @deprecated 以 playback_policy.allow_skip 为准 */
  can_skip_playback: boolean
  live_active: boolean
  battle_kind?: import('./autochess').BattleKind
  playback_policy?: import('./autochess').PlaybackPolicy
}

export interface DaoContestLiveTick {
  seq: number
  at_offset_ms: number
  phase: string
  kind: string
  audience?: string
  label_zh?: string
  remaining_seconds?: number
  dramatic?: boolean
  formation?: Record<string, unknown>
  event?: Record<string, unknown>
}

export interface DaoContestLiveStatePayload {
  match: DaoContestMatchPublic
  viewer_role: 'participant' | 'spectator' | string
  phase: 'prep' | 'battle' | 'ended' | 'replay' | string
  phase_label_zh?: string
  live_active: boolean
  /** @deprecated 以 playback_policy.allow_skip 为准 */
  can_skip: boolean
  countdown_seconds: number
  elapsed_ms?: number
  prep_seconds?: number
  playback_seconds?: number
  prep_ends_at?: string | null
  battle_ends_at?: string | null
  /** 直播已揭示的对战事件数（中途观战对齐用） */
  battle_event_cursor?: number
  server_now?: string | null
  formation_visible: boolean
  formation?: {
    side_a?: { character_id?: number | null; name?: string | null; label_zh?: string }
    side_b?: { character_id?: number | null; name?: string | null; label_zh?: string }
    hint_zh?: string
  } | null
  spectator_prep_hint_zh?: string | null
  visible_ticks: DaoContestLiveTick[]
  room_id?: string
  message?: string
  battle_kind?: import('./autochess').BattleKind
  playback_policy?: import('./autochess').PlaybackPolicy
}

export interface DaoContestSpectatePayload {
  match: DaoContestMatchPublic
  spectating: boolean
  live_active: boolean
  room_id?: string
  message?: string
  active_spectate_match_id?: number
}
