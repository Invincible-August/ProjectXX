/**
 * Cave (洞府) API: hub rooms + lab (研究室) desk.
 *
 * Canonical lab paths are `/cave/lab/*`. `/research/*` remains a backend alias.
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type { CaveOverviewPublic } from '../types/cave'
import type {
  PrivateContentPublic,
  ResearchCatalog,
  ResearchCreateRequest,
  ResearchSessionPublic,
} from '../types/research'

const LAB = '/cave/lab'

export async function fetchCaveOverviewApi(): Promise<ApiResponse<CaveOverviewPublic>> {
  try {
    const response = await http.get<ApiResponse<CaveOverviewPublic>>('/cave')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<CaveOverviewPublic>(error)
  }
}

export async function fetchResearchCatalogApi(): Promise<ApiResponse<ResearchCatalog>> {
  try {
    const response = await http.get<ApiResponse<ResearchCatalog>>(`${LAB}/catalog`)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<ResearchCatalog>(error)
  }
}

export async function createResearchSessionApi(
  payload: ResearchCreateRequest,
): Promise<ApiResponse<ResearchSessionPublic>> {
  try {
    const response = await http.post<ApiResponse<ResearchSessionPublic>>(
      `${LAB}/sessions`,
      payload,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<ResearchSessionPublic>(error)
  }
}

export async function fetchOpenResearchSessionsApi(): Promise<
  ApiResponse<{ items: ResearchSessionPublic[] }>
> {
  try {
    const response = await http.get<ApiResponse<{ items: ResearchSessionPublic[] }>>(
      `${LAB}/sessions`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{ items: ResearchSessionPublic[] }>(error)
  }
}

export async function fetchResearchSessionApi(
  sessionId: number,
): Promise<ApiResponse<ResearchSessionPublic>> {
  try {
    const response = await http.get<ApiResponse<ResearchSessionPublic>>(
      `${LAB}/sessions/${sessionId}`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<ResearchSessionPublic>(error)
  }
}

export async function rerollResearchSessionApi(
  sessionId: number,
): Promise<ApiResponse<ResearchSessionPublic>> {
  try {
    const response = await http.post<ApiResponse<ResearchSessionPublic>>(
      `${LAB}/sessions/${sessionId}/reroll`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<ResearchSessionPublic>(error)
  }
}

export async function finalizeResearchSessionApi(
  sessionId: number,
  labelZh: string,
): Promise<ApiResponse<ResearchSessionPublic>> {
  try {
    const response = await http.post<ApiResponse<ResearchSessionPublic>>(
      `${LAB}/sessions/${sessionId}/finalize`,
      { label_zh: labelZh },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<ResearchSessionPublic>(error)
  }
}

export async function submitResearchReviewApi(
  sessionId: number,
): Promise<ApiResponse<unknown>> {
  try {
    const response = await http.post<ApiResponse<unknown>>(
      `${LAB}/sessions/${sessionId}/submit-review`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function saveResearchDraftApi(
  sessionId: number,
  body: { blueprint?: Record<string, unknown>; effect_id?: string },
): Promise<ApiResponse<ResearchSessionPublic>> {
  try {
    const response = await http.post<ApiResponse<ResearchSessionPublic>>(
      `${LAB}/sessions/${sessionId}/draft`,
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<ResearchSessionPublic>(error)
  }
}

export async function fetchResearchMineApi(): Promise<
  ApiResponse<{ items: PrivateContentPublic[] }>
> {
  try {
    const response = await http.get<ApiResponse<{ items: PrivateContentPublic[] }>>(
      `${LAB}/mine`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{ items: PrivateContentPublic[] }>(error)
  }
}
