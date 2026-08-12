/**
 * M4 工坊 API：配方 / 队列 / 开工 / 领取。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type { CharacterPublic } from '../types/character'
import type { CraftActor, CraftClaimResult, CraftJob, CraftRecipe } from '../types/craft'

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
