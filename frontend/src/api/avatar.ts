/**
 * 化身 API：凝练 / 挂机 / 传修为 / 功能解锁 / 体力 / 探索·任务桩 / 神识。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type { CharacterPublic } from '../types/character'
import type {
  AvatarExploreStatus,
  AvatarFeaturesPayload,
  AvatarIdleDirection,
  AvatarPublic,
  AvatarTransferAudit,
  DivineSenseReading,
  TransferDirection,
} from '../types/avatar'

/** 通用响应：部分接口会附带 character */
export interface AvatarMutationPayload {
  character?: CharacterPublic
  avatar?: AvatarPublic
}

/** GET /avatar/me */
export async function fetchAvatar(): Promise<ApiResponse<AvatarPublic | null>> {
  try {
    const response = await http.get<ApiResponse<AvatarPublic | null>>('/avatar/me')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<AvatarPublic | null>(error)
  }
}

/** GET /avatar/features */
export async function fetchAvatarFeatures(): Promise<ApiResponse<AvatarFeaturesPayload>> {
  try {
    const response = await http.get<ApiResponse<AvatarFeaturesPayload>>('/avatar/features')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<AvatarFeaturesPayload>(error)
  }
}

/** POST /avatar/condense */
export async function condenseAvatar(): Promise<
  ApiResponse<AvatarMutationPayload | AvatarPublic>
> {
  try {
    const response = await http.post<ApiResponse<AvatarMutationPayload | AvatarPublic>>(
      '/avatar/condense',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<AvatarMutationPayload | AvatarPublic>(error)
  }
}

/** POST /avatar/idle */
export async function setAvatarIdle(
  direction: AvatarIdleDirection | string,
): Promise<ApiResponse<AvatarMutationPayload | AvatarPublic>> {
  try {
    const response = await http.post<ApiResponse<AvatarMutationPayload | AvatarPublic>>(
      '/avatar/idle',
      { direction },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<AvatarMutationPayload | AvatarPublic>(error)
  }
}

/** POST /avatar/transfer/preview */
export async function previewTransfer(body: {
  direction: TransferDirection
  resource?: 'cultivation_points'
  amount: number
}): Promise<ApiResponse<AvatarTransferAudit>> {
  try {
    const response = await http.post<ApiResponse<AvatarTransferAudit>>(
      '/avatar/transfer/preview',
      {
        resource: 'cultivation_points',
        ...body,
      },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<AvatarTransferAudit>(error)
  }
}

/** POST /avatar/transfer */
export async function transferCultivation(body: {
  direction: TransferDirection
  resource?: 'cultivation_points'
  amount: number
}): Promise<
  ApiResponse<
    AvatarMutationPayload &
      AvatarTransferAudit & {
        main_cultivation?: number
        avatar_cultivation?: number
      }
  >
> {
  try {
    const response = await http.post<
      ApiResponse<
        AvatarMutationPayload &
          AvatarTransferAudit & {
            main_cultivation?: number
            avatar_cultivation?: number
          }
      >
    >('/avatar/transfer', {
      resource: 'cultivation_points',
      ...body,
    })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<
      AvatarMutationPayload &
        AvatarTransferAudit & {
          main_cultivation?: number
          avatar_cultivation?: number
        }
    >(error)
  }
}

/** GET /avatar/sense */
export async function fetchDivineSense(): Promise<ApiResponse<DivineSenseReading>> {
  try {
    const response = await http.get<ApiResponse<DivineSenseReading>>('/avatar/sense')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<DivineSenseReading>(error)
  }
}

/** GET /avatar/explore/status */
export async function fetchExploreStatus(): Promise<ApiResponse<AvatarExploreStatus>> {
  try {
    const response = await http.get<ApiResponse<AvatarExploreStatus>>('/avatar/explore/status')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<AvatarExploreStatus>(error)
  }
}

/** POST /avatar/quests/accept 桩 */
export async function acceptAvatarQuest(questKind: 'npc' | 'sect'): Promise<
  ApiResponse<{
    ok: boolean
    code: number
    implemented: boolean
    quest_kind: string
    message: string
    avatar?: AvatarPublic
  }>
> {
  try {
    const response = await http.post('/avatar/quests/accept', { quest_kind: questKind })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** 助战会话摘要 */
export interface AvatarAssistSessionPublic {
  id: number
  status: string
  owner_character_id: number
  borrower_character_id: number
  avatar_id: number
  owner_name?: string
  borrower_name?: string
  avatar_name?: string
  expires_at?: string | null
  message?: string
}

/** POST /avatar/assist/settings */
export async function setAvatarAssistSettings(
  enabled: boolean,
): Promise<ApiResponse<{ message?: string; enabled?: boolean; avatar?: AvatarPublic }>> {
  try {
    const response = await http.post('/avatar/assist/settings', { enabled })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /avatar/assist/invite */
export async function inviteAvatarAssist(body: {
  target_character_id?: number | null
  target_name?: string | null
}): Promise<ApiResponse<{ message?: string; session?: AvatarAssistSessionPublic }>> {
  try {
    const response = await http.post('/avatar/assist/invite', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /avatar/assist/{id}/accept */
export async function acceptAvatarAssist(
  sessionId: number,
): Promise<ApiResponse<{ message?: string; session?: AvatarAssistSessionPublic }>> {
  try {
    const response = await http.post(`/avatar/assist/${sessionId}/accept`)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /avatar/assist/{id}/reject */
export async function rejectAvatarAssist(
  sessionId: number,
): Promise<ApiResponse<{ message?: string }>> {
  try {
    const response = await http.post(`/avatar/assist/${sessionId}/reject`)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /avatar/assist/{id}/end */
export async function endAvatarAssist(
  sessionId: number,
): Promise<ApiResponse<{ message?: string }>> {
  try {
    const response = await http.post(`/avatar/assist/${sessionId}/end`)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /avatar/assist/me */
export async function fetchAvatarAssistMe(): Promise<
  ApiResponse<{
    owned?: AvatarAssistSessionPublic[]
    borrowed?: AvatarAssistSessionPublic[]
    incoming?: AvatarAssistSessionPublic[]
    items?: AvatarAssistSessionPublic[]
  }>
> {
  try {
    const response = await http.get('/avatar/assist/me')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}
