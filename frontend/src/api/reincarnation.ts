/**
 * M5 轮回 API：预览 / 祭坛 / 流水 / 新生 / 商店。
 */
import { http } from './http'
import type { ApiResponse } from '../types/api'
import type {
  CompleteNewbornRequest,
  NewbornOptions,
  ReincarnationLogsPayload,
  ReincarnationPath,
  ReincarnationPreview,
  ReincarnationResult,
  ReincarnationShopCatalog,
} from '../types/reincarnation'

/** POST /reincarnation/preview */
export async function previewReincarnation(
  body?: { path?: ReincarnationPath },
): Promise<ApiResponse<ReincarnationPreview>> {
  const { data } = await http.post<ApiResponse<ReincarnationPreview>>(
    '/reincarnation/preview',
    body ?? {},
  )
  return data
}

/** POST /reincarnation/altar */
export async function altarReincarnation(
  body: { confirm: boolean },
): Promise<ApiResponse<ReincarnationResult>> {
  const { data } = await http.post<ApiResponse<ReincarnationResult>>(
    '/reincarnation/altar',
    body,
  )
  return data
}

/** GET /reincarnation/logs */
export async function fetchReincarnationLogs(
  limit = 20,
): Promise<ApiResponse<ReincarnationLogsPayload>> {
  const { data } = await http.get<ApiResponse<ReincarnationLogsPayload>>(
    '/reincarnation/logs',
    { params: { limit } },
  )
  return data
}

/** GET /reincarnation/newborn */
export async function fetchNewbornOptions(): Promise<ApiResponse<NewbornOptions>> {
  const { data } = await http.get<ApiResponse<NewbornOptions>>('/reincarnation/newborn')
  return data
}

/** POST /reincarnation/complete-newborn */
export async function completeNewborn(
  body: CompleteNewbornRequest,
): Promise<ApiResponse<ReincarnationResult & { completed?: boolean }>> {
  const { data } = await http.post<
    ApiResponse<ReincarnationResult & { completed?: boolean }>
  >('/reincarnation/complete-newborn', body)
  return data
}

/** GET /reincarnation/shop */
export async function fetchReincarnationShop(): Promise<
  ApiResponse<ReincarnationShopCatalog>
> {
  const { data } = await http.get<ApiResponse<ReincarnationShopCatalog>>(
    '/reincarnation/shop',
  )
  return data
}

/** POST /reincarnation/shop/buy */
export async function buyReincarnationShopItem(
  itemId: string,
  source: 'fixed' | 'random' = 'fixed',
): Promise<ApiResponse<ReincarnationResult & { purchased?: unknown }>> {
  const { data } = await http.post<
    ApiResponse<ReincarnationResult & { purchased?: unknown }>
  >('/reincarnation/shop/buy', { item_id: itemId, source })
  return data
}

/** POST /reincarnation/shop/refresh */
export async function refreshReincarnationShop(
  currency: 'points' | 'fate_luck' = 'points',
): Promise<
  ApiResponse<
    ReincarnationShopCatalog & {
      refreshed?: boolean
      message?: string
      character?: import('../types/character').CharacterPublic
    }
  >
> {
  const { data } = await http.post<
    ApiResponse<
      ReincarnationShopCatalog & {
        refreshed?: boolean
        message?: string
        character?: import('../types/character').CharacterPublic
      }
    >
  >('/reincarnation/shop/refresh', { currency })
  return data
}
