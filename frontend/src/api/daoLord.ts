/**
 * M6 道主 HTTP API：board / windows / claim / contests。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  DaoLordBoardPayload,
  DaoLordWindowsPayload,
} from '../types/daoLord'
import type { CharacterPublic } from '../types/character'

/** GET /dao-lord/board */
export async function fetchDaoLordBoard(): Promise<ApiResponse<DaoLordBoardPayload>> {
  try {
    const response = await http.get<ApiResponse<DaoLordBoardPayload>>('/dao-lord/board')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<DaoLordBoardPayload>(error)
  }
}

/** GET /dao-lord/windows */
export async function fetchDaoLordWindows(): Promise<
  ApiResponse<DaoLordWindowsPayload>
> {
  try {
    const response = await http.get<ApiResponse<DaoLordWindowsPayload>>(
      '/dao-lord/windows',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<DaoLordWindowsPayload>(error)
  }
}

/**
 * POST /dao-lord/claim — 兼容入口：空位自动就任（有主须走赛会）。
 *
 * @param body - 目标道 id
 */
export async function claimDaoLord(body: {
  dao_id: string
}): Promise<
  ApiResponse<{
    seat?: import('../types/daoLord').DaoLordSeatPublic
    character?: CharacterPublic
    message?: string
  }>
> {
  try {
    const response = await http.post<
      ApiResponse<{
        seat?: import('../types/daoLord').DaoLordSeatPublic
        character?: CharacterPublic
        message?: string
      }>
    >('/dao-lord/claim', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /dao-lord/contests/current */
export async function fetchDaoContestCurrent(): Promise<
  ApiResponse<import('../types/daoLord').DaoContestCurrentPayload>
> {
  try {
    const response = await http.get<
      ApiResponse<import('../types/daoLord').DaoContestCurrentPayload>
    >('/dao-lord/contests/current')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /dao-lord/contests/current/register */
export async function registerDaoContest(): Promise<
  ApiResponse<import('../types/daoLord').DaoContestCurrentPayload>
> {
  try {
    const response = await http.post<
      ApiResponse<import('../types/daoLord').DaoContestCurrentPayload>
    >('/dao-lord/contests/current/register')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** DELETE /dao-lord/contests/current/register */
export async function unregisterDaoContest(): Promise<
  ApiResponse<import('../types/daoLord').DaoContestCurrentPayload>
> {
  try {
    const response = await http.delete<
      ApiResponse<import('../types/daoLord').DaoContestCurrentPayload>
    >('/dao-lord/contests/current/register')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /dao-lord/contests/current/rsvp */
export async function submitDaoContestRsvp(accept: boolean): Promise<
  ApiResponse<import('../types/daoLord').DaoContestCurrentPayload>
> {
  try {
    const response = await http.post<
      ApiResponse<import('../types/daoLord').DaoContestCurrentPayload>
    >('/dao-lord/contests/current/rsvp', { accept })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /dao-lord/contests/current/arena */
export async function fetchDaoContestArena(): Promise<
  ApiResponse<import('../types/daoLord').DaoContestArenaPayload>
> {
  try {
    const response = await http.get<
      ApiResponse<import('../types/daoLord').DaoContestArenaPayload>
    >('/dao-lord/contests/current/arena')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /dao-lord/contests/current/arena/enter */
export async function enterDaoContestArena(): Promise<
  ApiResponse<import('../types/daoLord').DaoContestArenaPayload>
> {
  try {
    const response = await http.post<
      ApiResponse<import('../types/daoLord').DaoContestArenaPayload>
    >('/dao-lord/contests/current/arena/enter')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /dao-lord/contests/current/arena/leave（判负由服务端决定） */
export async function leaveDaoContestArena(): Promise<
  ApiResponse<import('../types/daoLord').DaoContestArenaPayload>
> {
  try {
    const response = await http.post<
      ApiResponse<import('../types/daoLord').DaoContestArenaPayload>
    >('/dao-lord/contests/current/arena/leave', {})
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /dao-lord/contests/current/bracket */
export async function fetchDaoContestBracket(daoId?: string | null): Promise<
  ApiResponse<import('../types/daoLord').DaoContestBracketPayload>
> {
  try {
    const response = await http.get<
      ApiResponse<import('../types/daoLord').DaoContestBracketPayload>
    >('/dao-lord/contests/current/bracket', {
      params: daoId ? { dao_id: daoId } : undefined,
    })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /dao-lord/contests/matches/{id} */
export async function fetchDaoContestMatch(matchId: number): Promise<
  ApiResponse<{ match: import('../types/daoLord').DaoContestMatchPublic }>
> {
  try {
    const response = await http.get<
      ApiResponse<{ match: import('../types/daoLord').DaoContestMatchPublic }>
    >(`/dao-lord/contests/matches/${matchId}`)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /dao-lord/contests/matches/{id}/report */
export async function fetchDaoContestMatchReport(matchId: number): Promise<
  ApiResponse<import('../types/daoLord').DaoContestMatchReportPayload>
> {
  try {
    const response = await http.get<
      ApiResponse<import('../types/daoLord').DaoContestMatchReportPayload>
    >(`/dao-lord/contests/matches/${matchId}/report`)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /dao-lord/contests/matches/{id}/live */
export async function fetchDaoContestMatchLive(matchId: number): Promise<
  ApiResponse<import('../types/daoLord').DaoContestLiveStatePayload>
> {
  try {
    const response = await http.get<
      ApiResponse<import('../types/daoLord').DaoContestLiveStatePayload>
    >(`/dao-lord/contests/matches/${matchId}/live`)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /dao-lord/contests/matches/{id}/spectate */
export async function spectateDaoContestMatch(matchId: number): Promise<
  ApiResponse<import('../types/daoLord').DaoContestSpectatePayload>
> {
  try {
    const response = await http.post<
      ApiResponse<import('../types/daoLord').DaoContestSpectatePayload>
    >(`/dao-lord/contests/matches/${matchId}/spectate`, {})
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}
