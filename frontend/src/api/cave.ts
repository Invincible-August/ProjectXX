/**
 * Cave (洞府) API: hub rooms + lab (研究室) desk.
 *
 * Canonical lab paths are `/cave/lab/*`. `/research/*` remains a backend alias.
 * Workshop play page is `/cave/workshop`; craft HTTP stays `/craft`.
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
import type {
  TechniqueCultivatePublic,
  TechniqueDraftPublic,
} from '../types/techniqueCraft'

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

const TECH = `${LAB}/technique`

export async function fetchTechniqueDraftsApi(): Promise<
  ApiResponse<{ items: TechniqueDraftPublic[] }>
> {
  try {
    const response = await http.get<ApiResponse<{ items: TechniqueDraftPublic[] }>>(
      `${TECH}/drafts`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{ items: TechniqueDraftPublic[] }>(error)
  }
}

export async function createTechniqueDraftApi(): Promise<ApiResponse<TechniqueDraftPublic>> {
  try {
    const response = await http.post<ApiResponse<TechniqueDraftPublic>>(`${TECH}/drafts`)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TechniqueDraftPublic>(error)
  }
}

export async function abandonTechniqueDraftApi(
  draftId: number,
): Promise<ApiResponse<Record<string, never>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, never>>>(
      `${TECH}/drafts/${draftId}/abandon`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<Record<string, never>>(error)
  }
}

export async function embedTechniqueCardApi(
  draftId: number,
  itemUid: string,
): Promise<ApiResponse<TechniqueDraftPublic>> {
  try {
    const response = await http.post<ApiResponse<TechniqueDraftPublic>>(
      `${TECH}/drafts/${draftId}/embed`,
      { item_uid: itemUid },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TechniqueDraftPublic>(error)
  }
}

export async function setTechniqueConditionsApi(
  draftId: number,
  body: { element_limit?: string | null; weapon_limit?: string | null },
): Promise<ApiResponse<TechniqueDraftPublic>> {
  try {
    const response = await http.post<ApiResponse<TechniqueDraftPublic>>(
      `${TECH}/drafts/${draftId}/conditions`,
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TechniqueDraftPublic>(error)
  }
}

export async function rollTechniqueAffixApi(
  draftId: number,
  slot: number,
): Promise<ApiResponse<TechniqueDraftPublic>> {
  try {
    const response = await http.post<ApiResponse<TechniqueDraftPublic>>(
      `${TECH}/drafts/${draftId}/affix/roll`,
      { slot },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TechniqueDraftPublic>(error)
  }
}

export async function chooseTechniqueAffixApi(
  draftId: number,
  slot: number,
  affixId: string,
): Promise<ApiResponse<TechniqueDraftPublic>> {
  try {
    const response = await http.post<ApiResponse<TechniqueDraftPublic>>(
      `${TECH}/drafts/${draftId}/affix/choose`,
      { slot, affix_id: affixId },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TechniqueDraftPublic>(error)
  }
}

export async function rerollTechniqueAffixApi(
  draftId: number,
  slot: number,
): Promise<ApiResponse<TechniqueDraftPublic>> {
  try {
    const response = await http.post<ApiResponse<TechniqueDraftPublic>>(
      `${TECH}/drafts/${draftId}/affix/reroll`,
      { slot },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TechniqueDraftPublic>(error)
  }
}

export async function finalizeTechniqueDraftApi(
  draftId: number,
  labelZh: string,
): Promise<ApiResponse<TechniqueDraftPublic>> {
  try {
    const response = await http.post<ApiResponse<TechniqueDraftPublic>>(
      `${TECH}/drafts/${draftId}/finalize`,
      { label_zh: labelZh },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TechniqueDraftPublic>(error)
  }
}

export async function upgradeTechniqueBaseApi(
  techniqueId: string,
  stat: 'attack' | 'defense' | 'speed',
): Promise<ApiResponse<TechniqueCultivatePublic>> {
  try {
    const response = await http.post<ApiResponse<TechniqueCultivatePublic>>(
      `${TECH}/techniques/${techniqueId}/base-upgrade`,
      { stat },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TechniqueCultivatePublic>(error)
  }
}

export async function upgradeTechniqueAffixApi(
  techniqueId: string,
  slot: number,
): Promise<ApiResponse<TechniqueCultivatePublic>> {
  try {
    const response = await http.post<ApiResponse<TechniqueCultivatePublic>>(
      `${TECH}/techniques/${techniqueId}/affix-upgrade`,
      { slot },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TechniqueCultivatePublic>(error)
  }
}

export async function rollCultivateAffixApi(
  techniqueId: string,
  slot: number,
): Promise<ApiResponse<TechniqueCultivatePublic>> {
  try {
    const response = await http.post<ApiResponse<TechniqueCultivatePublic>>(
      `${TECH}/techniques/${techniqueId}/affix/roll`,
      { slot },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TechniqueCultivatePublic>(error)
  }
}

export async function chooseCultivateAffixApi(
  techniqueId: string,
  slot: number,
  affixId: string,
): Promise<ApiResponse<TechniqueCultivatePublic>> {
  try {
    const response = await http.post<ApiResponse<TechniqueCultivatePublic>>(
      `${TECH}/techniques/${techniqueId}/affix/choose`,
      { slot, affix_id: affixId },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TechniqueCultivatePublic>(error)
  }
}

export async function rerollCultivateAffixApi(
  techniqueId: string,
  slot: number,
): Promise<ApiResponse<TechniqueCultivatePublic>> {
  try {
    const response = await http.post<ApiResponse<TechniqueCultivatePublic>>(
      `${TECH}/techniques/${techniqueId}/affix/reroll`,
      { slot },
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TechniqueCultivatePublic>(error)
  }
}

export async function breakthroughTechniqueApi(
  techniqueId: string,
): Promise<ApiResponse<TechniqueCultivatePublic>> {
  try {
    const response = await http.post<ApiResponse<TechniqueCultivatePublic>>(
      `${TECH}/techniques/${techniqueId}/breakthrough`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<TechniqueCultivatePublic>(error)
  }
}

export async function printTechniqueManualApi(
  techniqueId: string,
): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      `${TECH}/techniques/${techniqueId}/print-manual`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<Record<string, unknown>>(error)
  }
}

export async function abolishTechniqueApi(
  techniqueId: string,
): Promise<ApiResponse<{ technique_id: string; abolished: boolean }>> {
  try {
    const response = await http.post<ApiResponse<{ technique_id: string; abolished: boolean }>>(
      `${TECH}/techniques/${techniqueId}/abolish`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{ technique_id: string; abolished: boolean }>(error)
  }
}
