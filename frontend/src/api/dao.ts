/**
 * M6 大道 HTTP API：catalog / me / pool / open / usage preview。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  DaoCatalogPayload,
  DaoChooseResult,
  DaoOpenOffer,
  DaoPoolPayload,
  DaoPublic,
  DaoUsageContext,
  DaoUsagePreview,
} from '../types/dao'
import type { CharacterPublic } from '../types/character'

/** GET /dao/catalog */
export async function fetchDaoCatalog(): Promise<ApiResponse<DaoCatalogPayload>> {
  try {
    const response = await http.get<ApiResponse<DaoCatalogPayload>>('/dao/catalog')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<DaoCatalogPayload>(error)
  }
}

/** GET /dao/me */
export async function fetchDaoMe(): Promise<ApiResponse<DaoPublic>> {
  try {
    const response = await http.get<ApiResponse<DaoPublic>>('/dao/me')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<DaoPublic>(error)
  }
}

/** GET /dao/pool */
export async function fetchDaoPool(): Promise<ApiResponse<DaoPoolPayload>> {
  try {
    const response = await http.get<ApiResponse<DaoPoolPayload>>('/dao/pool')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<DaoPoolPayload>(error)
  }
}

/** POST /dao/open/roll — 冻结三选项；重复 roll 由服务端拒绝（40096） */
export async function rollDaoOpen(): Promise<
  ApiResponse<DaoOpenOffer & { character?: CharacterPublic; message?: string }>
> {
  try {
    const response = await http.post<
      ApiResponse<DaoOpenOffer & { character?: CharacterPublic; message?: string }>
    >('/dao/open/roll', {})
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<
      DaoOpenOffer & { character?: CharacterPublic; message?: string }
    >(error)
  }
}

/**
 * POST /dao/open/choose — 锁定本命道。
 *
 * @param body - session_id + 选定 dao_id（三选一或合法道池自选）
 */
export async function chooseDaoOpen(body: {
  session_id: string
  dao_id: string
}): Promise<ApiResponse<DaoChooseResult>> {
  try {
    const response = await http.post<ApiResponse<DaoChooseResult>>(
      '/dao/open/choose',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<DaoChooseResult>(error)
  }
}

/**
 * POST /dao/usage/preview — 战斗/工坊运用消耗预览（可选）。
 *
 * @param body - 场景上下文
 */
export async function previewDaoUsage(body: {
  context: DaoUsageContext
}): Promise<ApiResponse<DaoUsagePreview>> {
  try {
    const response = await http.post<ApiResponse<DaoUsagePreview>>(
      '/dao/usage/preview',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<DaoUsagePreview>(error)
  }
}
