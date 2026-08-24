/**
 * M4 工坊 API：配方 / 队列 / 开工 / 领取。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type { CharacterPublic } from '../types/character'
import type {
  CraftActor,
  CraftClaimResult,
  CraftJob,
  CraftRecipe,
  TalismanPreloadPayload,
} from '../types/craft'

export interface CraftStartPayload {
  character?: CharacterPublic
  job?: CraftJob
}

export interface CraftClaimPayload extends CraftClaimResult {
  character?: CharacterPublic
}

/** GET /craft/recipes */
export async function fetchRecipes(): Promise<ApiResponse<{ recipes: CraftRecipe[] }>> {
  try {
    const response = await http.get<ApiResponse<{ recipes: CraftRecipe[] }>>('/craft/recipes')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{ recipes: CraftRecipe[] }>(error)
  }
}

/** GET /craft/jobs */
export async function fetchJobs(): Promise<ApiResponse<{ jobs: CraftJob[] }>> {
  try {
    const response = await http.get<ApiResponse<{ jobs: CraftJob[] }>>('/craft/jobs')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{ jobs: CraftJob[] }>(error)
  }
}

/** POST /craft/start */
export async function startCraft(body: {
  recipe_id: string
  actor: CraftActor
  use_dao?: boolean
}): Promise<ApiResponse<CraftStartPayload | CraftJob>> {
  try {
    const response = await http.post<ApiResponse<CraftStartPayload | CraftJob>>(
      '/craft/start',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<CraftStartPayload | CraftJob>(error)
  }
}

/** POST /craft/talisman/scribe */
export async function scribeTalismanApi(body: {
  template_id: string
  quantity: number
}): Promise<ApiResponse<{ template_id: string; quantity: number; label_zh: string }>> {
  try {
    const response = await http.post<
      ApiResponse<{ template_id: string; quantity: number; label_zh: string }>
    >('/craft/talisman/scribe', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /craft/talisman/preload */
export async function fetchTalismanPreloadApi(): Promise<ApiResponse<TalismanPreloadPayload>> {
  try {
    const response = await http.get<ApiResponse<TalismanPreloadPayload>>('/craft/talisman/preload')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TalismanPreloadPayload>(error)
  }
}

/** PUT /craft/talisman/preload */
export async function putTalismanPreloadApi(
  inventoryItemIds: number[],
): Promise<ApiResponse<TalismanPreloadPayload>> {
  try {
    const response = await http.put<ApiResponse<TalismanPreloadPayload>>('/craft/talisman/preload', {
      inventory_item_ids: inventoryItemIds,
    })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TalismanPreloadPayload>(error)
  }
}

/** POST /craft/claim */
export async function claimCraft(jobId: number): Promise<ApiResponse<CraftClaimPayload>> {
  try {
    const response = await http.post<ApiResponse<CraftClaimPayload>>('/craft/claim', {
      job_id: jobId,
    })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<CraftClaimPayload>(error)
  }
}
