/** 运营干预 API：道主剔除 / 赛会立刻开赛 / 重新开放报名 / 跳过等待。 */
import { http, unwrap } from './http'

export interface DaoLordSeatRow {
  dao_id: string
  dao_label: string
  lord_character_id?: number | null
  lord_name?: string | null
  claimed_at?: string | null
  vacant: boolean
}

export interface DaoContestOpsHints {
  settle_when_zh: string
  reopen_when_zh: string
  force_start_requires: string
  can_force_start: boolean
  can_reopen: boolean
  can_advance_arena?: boolean
  advance_arena_zh?: string
  current_phase?: string | null
}

export interface DaoContestOpsPayload {
  contest: {
    id: number
    cycle_date: string
    status: string
    status_label: string
    eta_label: string
    total_entrants: number
    can_register: boolean
    fight_at?: string | null
    force_started?: boolean
    phase?: string | null
    match_count?: number
  }
  me?: { registered: boolean }
  message?: string
  ops_hints?: DaoContestOpsHints
  ops_advance?: {
    steps: Array<{ from: string; to: string; status: string }>
    until_playing: boolean
  }
}

export async function fetchDaoLords() {
  return unwrap<{ seats: DaoLordSeatRow[] }>(http.get('/ops/dao-lords'))
}

export async function removeDaoLord(daoId: string, note?: string) {
  return unwrap<{
    dao_id: string
    dao_label: string
    removed: boolean
    former_character_id?: number
    aborted_challenge_id?: number | null
    message?: string
  }>(http.post(`/ops/dao-lords/${encodeURIComponent(daoId)}/remove`, { note: note || null }))
}

export async function fetchDaoContest() {
  return unwrap<DaoContestOpsPayload>(http.get('/ops/dao-contests/current'))
}

export async function forceStartDaoContest(note?: string) {
  return unwrap<DaoContestOpsPayload>(
    http.post('/ops/dao-contests/force-start', { note: note || null }),
  )
}

/** 清空本场报名/对阵并回到报名中（联调反复开赛） */
export async function reopenDaoContest(note?: string) {
  return unwrap<DaoContestOpsPayload>(
    http.post('/ops/dao-contests/reopen', { note: note || null }),
  )
}

/** 跳过整备/倒计时/轮间/直播，推进至对战演出 */
export async function advanceDaoContestArena(note?: string, untilPlaying = true) {
  return unwrap<DaoContestOpsPayload>(
    http.post('/ops/dao-contests/advance-arena', {
      note: note || null,
      until_playing: untilPlaying,
    }),
  )
}
