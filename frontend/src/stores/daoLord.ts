/**
 * M6 道主 Pinia store：榜单 / 开窗 / 道主之争赛会。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  claimDaoLord,
  enterDaoContestArena,
  fetchDaoContestArena,
  fetchDaoContestBracket,
  fetchDaoContestCurrent,
  fetchDaoContestMatchLive,
  fetchDaoContestMatchReport,
  fetchDaoLordBoard,
  fetchDaoLordWindows,
  leaveDaoContestArena,
  registerDaoContest,
  spectateDaoContestMatch,
  submitDaoContestRsvp,
  unregisterDaoContest,
} from '../api/daoLord'
import type {
  DaoContestArenaPayload,
  DaoContestBracketPayload,
  DaoContestCurrentPayload,
  DaoContestLiveStatePayload,
  DaoContestMatchReportPayload,
  DaoLordSeatPublic,
  DaoLordWindowPublic,
} from '../types/daoLord'
import type { WsEnvelope } from '../types/ws'
import { isDaoLordRoomType, WsType } from '../ws/protocol'
import { useCharacterStore } from './character'

export const useDaoLordStore = defineStore('daoLord', () => {
  const board = ref<DaoLordSeatPublic[]>([])
  const window = ref<DaoLordWindowPublic | null>(null)
  const contest = ref<DaoContestCurrentPayload | null>(null)
  const bracket = ref<DaoContestBracketPayload | null>(null)
  const matchReport = ref<DaoContestMatchReportPayload | null>(null)
  const liveState = ref<DaoContestLiveStatePayload | null>(null)
  const arena = ref<DaoContestArenaPayload | null>(null)
  const loading = ref(false)
  const lastMessage = ref('')
  /** 开赛推送后自动打开的直播对阵 id（ContestPanel 消费后清空） */
  const pendingLiveMatchId = ref<number | null>(null)
  /** 递增信号：DaoLordView 切到赛会 Tab */
  const contestKickSignal = ref(0)
  /** RSVP 弹框去重 */
  const rsvpPromptedContestId = ref<number | null>(null)

  const isWindowOpen = computed(() => Boolean(window.value?.open))

  /**
   * 拉取榜单 + 开窗 + 赛会；空位达标时服务端惰性自动就任。
   */
  async function refresh(): Promise<string | null> {
    loading.value = true
    try {
      const [boardEnv, winEnv, contestEnv] = await Promise.all([
        fetchDaoLordBoard(),
        fetchDaoLordWindows(),
        fetchDaoContestCurrent(),
      ])
      if (boardEnv.code !== 0 || !boardEnv.data) {
        return boardEnv.message || `加载道主榜失败（code=${boardEnv.code}）`
      }
      board.value = boardEnv.data.seats ?? []
      const auto = boardEnv.data.auto_inaugurated
      if (auto?.message) {
        lastMessage.value = auto.message
      } else {
        lastMessage.value = ''
      }
      if (winEnv.code === 0 && winEnv.data) {
        window.value = winEnv.data.window
      }
      if (contestEnv.code === 0 && contestEnv.data) {
        contest.value = contestEnv.data
      }
      return null
    } finally {
      loading.value = false
    }
  }

  async function refreshContest(): Promise<string | null> {
    const envelope = await fetchDaoContestCurrent()
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '加载赛会失败'
    }
    contest.value = envelope.data
    return null
  }

  async function registerContest(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await registerDaoContest()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `报名失败（code=${envelope.code}）`
      }
      contest.value = envelope.data
      lastMessage.value = envelope.data.message || '报名成功'
      return null
    } finally {
      loading.value = false
    }
  }

  async function unregisterContest(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await unregisterDaoContest()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `取消报名失败（code=${envelope.code}）`
      }
      contest.value = envelope.data
      lastMessage.value = envelope.data.message || '已取消报名'
      return null
    } finally {
      loading.value = false
    }
  }

  async function refreshBracket(daoId?: string | null): Promise<string | null> {
    const envelope = await fetchDaoContestBracket(daoId)
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '加载对阵失败'
    }
    bracket.value = envelope.data
    return null
  }

  async function loadMatchReport(matchId: number): Promise<string | null> {
    const envelope = await fetchDaoContestMatchReport(matchId)
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '加载战报失败'
    }
    matchReport.value = envelope.data
    return null
  }

  async function spectateMatch(matchId: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await spectateDaoContestMatch(matchId)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `观战失败（code=${envelope.code}）`
      }
      lastMessage.value = envelope.data.message || '已进入观战'
      if (contest.value?.me) {
        contest.value = {
          ...contest.value,
          me: {
            ...contest.value.me,
            active_spectate_match_id: envelope.data.active_spectate_match_id ?? matchId,
          },
        }
      }
      await pollLive(matchId)
      return null
    } finally {
      loading.value = false
    }
  }

  /** 轮询直播时钟（准备倒计时 / 对战节拍）。 */
  async function pollLive(matchId: number): Promise<string | null> {
    const envelope = await fetchDaoContestMatchLive(matchId)
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '加载直播状态失败'
    }
    liveState.value = envelope.data
    return null
  }

  function clearLive(): void {
    liveState.value = null
  }

  async function refreshWindow(): Promise<string | null> {
    const envelope = await fetchDaoLordWindows()
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || null
    }
    window.value = envelope.data.window
    return null
  }

  /**
   * 兼容旧 API：空位自动就任（有主则失败，须挑战）。
   *
   * @param daoId - 目标道
   * @deprecated 优先依赖开道/升级/拉榜自动就任
   */
  async function claim(daoId: string): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await claimDaoLord({ dao_id: daoId })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `就任失败（code=${envelope.code}）`
      }
      if (envelope.data.character) {
        useCharacterStore().applyCharacter(envelope.data.character)
      }
      lastMessage.value = envelope.data.message || '空位自动就任成功'
      await refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 处理赛会状态推送：RSVP / 刷新对阵 / 标记直播场次。
   *
   * @param payload - ``dao_lord.contest.state`` payload
   */
  async function handleContestState(payload: Record<string, unknown>): Promise<void> {
    const messageZh = String(payload.message_zh || '道主之争状态更新')
    lastMessage.value = messageZh
    contestKickSignal.value += 1

    await refreshContest()
    const action = String(payload.action || '')
    if (action === 'rsvp_open' || contest.value?.me?.needs_rsvp) {
      // WS 层弹框；此处只刷新
    }
    const daoId = contest.value?.me?.dao_id || undefined
    if (
      contest.value?.contest?.bracket_ready ||
      contest.value?.contest?.status === 'arena' ||
      contest.value?.contest?.status === 'rsvp'
    ) {
      await refreshBracket(daoId)
      await refreshArena()
    }

    const meId = bracket.value?.me_character_id
    const list = bracket.value?.matches || []
    // 仅自动打开「本人参战」的直播，勿强拉任意场次
    const mineLive = list.find(
      (m) =>
        m.live_active &&
        meId != null &&
        (m.side_a?.character_id === meId || m.side_b?.character_id === meId),
    )
    pendingLiveMatchId.value = mineLive?.id ?? null
  }

  async function submitRsvp(accept: boolean): Promise<string | null> {
    const envelope = await submitDaoContestRsvp(accept)
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '入席确认失败'
    }
    contest.value = envelope.data
    lastMessage.value = envelope.data.message || (accept ? '已确认前往擂台' : '已确认')
    if (accept) {
      await enterArena()
    }
    return null
  }

  async function refreshArena(): Promise<string | null> {
    const envelope = await fetchDaoContestArena()
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '加载擂台失败'
    }
    arena.value = envelope.data
    return null
  }

  async function enterArena(): Promise<string | null> {
    const envelope = await enterDaoContestArena()
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '进入擂台失败'
    }
    arena.value = envelope.data
    return null
  }

  async function leaveArena(_forfeitIgnored = true): Promise<string | null> {
    // 判负由服务端权威决定；参数仅兼容旧调用点
    const envelope = await leaveDaoContestArena()
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '离开擂台失败'
    }
    arena.value = envelope.data
    return null
  }

  function clearPendingLiveMatch(): void {
    pendingLiveMatchId.value = null
  }

  /**
   * 处理入站信封（由 ws store 或页面订阅调用）。
   *
   * 旧单挑 room.state / battle.event 已移除；赛会态由 ws store 全局 handleContestState。
   *
   * @param envelope - WS 信封
   */
  function onWsEnvelope(envelope: WsEnvelope): void {
    if (envelope.type === WsType.DAO_LORD_CONTEST_STATE) {
      return
    }
    if (!isDaoLordRoomType(envelope.type)) return
  }

  return {
    board,
    window,
    contest,
    bracket,
    matchReport,
    liveState,
    arena,
    loading,
    lastMessage,
    pendingLiveMatchId,
    contestKickSignal,
    rsvpPromptedContestId,
    isWindowOpen,
    refresh,
    refreshWindow,
    refreshContest,
    registerContest,
    unregisterContest,
    refreshBracket,
    loadMatchReport,
    spectateMatch,
    pollLive,
    clearLive,
    clearPendingLiveMatch,
    handleContestState,
    submitRsvp,
    refreshArena,
    enterArena,
    leaveArena,
    claim,
    onWsEnvelope,
  }
})
