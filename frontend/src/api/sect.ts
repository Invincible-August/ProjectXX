/**
 * M7 L1 宗门 HTTP API：me / npc / join / create / quests / shop / lamps / exchange。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  ExchangeCatalogPayload,
  NpcSectListPayload,
  SectJoinCreateResult,
  SectMePayload,
  SectPetExchangeResult,
  SectQuestActionResult,
  SectQuestListPayload,
  SectShopBuyResult,
  SectShopPayload,
  SoulLampListPayload,
} from '../types/sect'

/** GET /sect/me */
export async function fetchSectMe(): Promise<ApiResponse<SectMePayload>> {
  try {
    const response = await http.get<ApiResponse<SectMePayload>>('/sect/me')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<SectMePayload>(error)
  }
}

/** GET /sect/npc */
export async function fetchSectNpc(): Promise<ApiResponse<NpcSectListPayload>> {
  try {
    const response = await http.get<ApiResponse<NpcSectListPayload>>('/sect/npc')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<NpcSectListPayload>(error)
  }
}

/**
 * POST /sect/join — 拜入 NPC 宗门。
 *
 * @param body - template_id
 */
export async function joinSect(body: {
  template_id: string
}): Promise<ApiResponse<SectJoinCreateResult>> {
  try {
    const response = await http.post<ApiResponse<SectJoinCreateResult>>(
      '/sect/join',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<SectJoinCreateResult>(error)
  }
}

/**
 * POST /sect/create — 自建宗门。
 *
 * @param body - name + specialty + 可选 motto
 */
export async function createSect(body: {
  name: string
  specialty: string
  motto?: string | null
}): Promise<ApiResponse<SectJoinCreateResult>> {
  try {
    const response = await http.post<ApiResponse<SectJoinCreateResult>>(
      '/sect/create',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<SectJoinCreateResult>(error)
  }
}

/** GET /sect/overview */
export async function fetchSectOverview(): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.get<ApiResponse<Record<string, unknown>>>('/sect/overview')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /sect/members */
export async function fetchSectMembers(): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.get<ApiResponse<Record<string, unknown>>>('/sect/members')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /sect/ranks/applications */
export async function fetchRankApplications(): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.get<ApiResponse<Record<string, unknown>>>(
      '/sect/ranks/applications',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/ranks/apply */
export async function applySectRank(body: {
  target_rank: string
}): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/sect/ranks/apply',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/ranks/appoint */
export async function appointSectRank(body: {
  target_character_id: number
  target_rank: string
}): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/sect/ranks/appoint',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/council/salary */
export async function claimSectSalary(): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/sect/council/salary',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/council/announce */
export async function announceSect(body: {
  text_zh: string
}): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/sect/council/announce',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/council/war/start */
export async function startSectWar(body: {
  war_kind: string
}): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/sect/council/war/start',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/grade/upgrade */
export async function upgradeSectGrade(): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/sect/grade/upgrade',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/facilities/{id}/upgrade */
export async function upgradeSectFacility(
  facilityId: string,
): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      `/sect/facilities/${encodeURIComponent(facilityId)}/upgrade`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/buffs/toggle */
export async function toggleSectBuff(body: {
  buff_id: string
  enable: boolean
}): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/sect/buffs/toggle',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /sect/treasury */
export async function fetchTreasury(): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.get<ApiResponse<Record<string, unknown>>>('/sect/treasury')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/treasury/exchange */
export async function exchangeTreasury(body: {
  item_key: string
}): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/sect/treasury/exchange',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /sect/scripture */
export async function fetchScripture(): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.get<ApiResponse<Record<string, unknown>>>('/sect/scripture')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/scripture/exchange */
export async function exchangeScripture(body: {
  technique_id: string
}): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/sect/scripture/exchange',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /sect/workshops/{branch} */
export async function fetchWorkshop(
  branch: string,
): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.get<ApiResponse<Record<string, unknown>>>(
      `/sect/workshops/${encodeURIComponent(branch)}`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/workshops/{branch}/hire */
export async function hireWorkshop(
  branch: string,
  body: { craftsman_id: string; recipe_id: string },
): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      `/sect/workshops/${encodeURIComponent(branch)}/hire`,
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/workshops/{branch}/blueprints/exchange */
export async function exchangeWorkshopBlueprint(
  branch: string,
  body: { recipe_id: string },
): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      `/sect/workshops/${encodeURIComponent(branch)}/blueprints/exchange`,
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/workshops/{branch}/blueprints/donate */
export async function donateWorkshopBlueprint(
  branch: string,
  body: {
    recipe_id: string
    label_zh: string
    cost_contribution?: number
    self_research?: boolean
  },
): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      `/sect/workshops/${encodeURIComponent(branch)}/blueprints/donate`,
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /sect/formation */
export async function fetchFormation(): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.get<ApiResponse<Record<string, unknown>>>('/sect/formation')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/formation/select */
export async function selectFormation(body: {
  formation_id: string
}): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/sect/formation/select',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/formation/active */
export async function setFormationActive(body: {
  active: boolean
}): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/sect/formation/active',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/formation/allocate */
export async function allocateFormationAttr(body: {
  attr_key: string
}): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/sect/formation/allocate',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/formation/exchange */
export async function exchangeFormation(body: {
  formation_id: string
}): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/sect/formation/exchange',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/formation/donate */
export async function donateFormation(body: {
  formation_id: string
  need_review?: boolean
}): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/sect/formation/donate',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /sect/mine */
export async function fetchMine(): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.get<ApiResponse<Record<string, unknown>>>('/sect/mine')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/mine/start */
export async function startMine(): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>('/sect/mine/start')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/mine/stop */
export async function stopMine(): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>('/sect/mine/stop')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /sect/herbs */
export async function fetchHerbs(): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.get<ApiResponse<Record<string, unknown>>>('/sect/herbs')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/herbs/exchange */
export async function exchangeHerb(body: {
  plant_id: string
}): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/sect/herbs/exchange',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/herbs/plant */
export async function plantHerb(body: {
  plant_id: string
  herbalist_id?: string | null
  hosted?: boolean
}): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      '/sect/herbs/plant',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /sect/herbs/{id}/harvest */
export async function harvestHerb(
  plotId: number,
): Promise<ApiResponse<Record<string, unknown>>> {
  try {
    const response = await http.post<ApiResponse<Record<string, unknown>>>(
      `/sect/herbs/${plotId}/harvest`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** GET /sect/quests */
export async function fetchSectQuests(): Promise<ApiResponse<SectQuestListPayload>> {
  try {
    const response = await http.get<ApiResponse<SectQuestListPayload>>('/sect/quests')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<SectQuestListPayload>(error)
  }
}

/**
 * POST /sect/quests/{quest_id}/accept
 *
 * @param questId - 任务 id
 * @param body - assignee：body | avatar
 */
export async function acceptSectQuest(
  questId: string,
  body: { assignee: string },
): Promise<ApiResponse<SectQuestActionResult>> {
  try {
    const response = await http.post<ApiResponse<SectQuestActionResult>>(
      `/sect/quests/${encodeURIComponent(questId)}/accept`,
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<SectQuestActionResult>(error)
  }
}

/**
 * POST /sect/quests/{quest_id}/complete
 *
 * @param questId - 任务 id
 * @param body - assignee
 */
export async function completeSectQuest(
  questId: string,
  body: { assignee: string },
): Promise<ApiResponse<SectQuestActionResult>> {
  try {
    const response = await http.post<ApiResponse<SectQuestActionResult>>(
      `/sect/quests/${encodeURIComponent(questId)}/complete`,
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<SectQuestActionResult>(error)
  }
}

/** GET /sect/shop */
export async function fetchSectShop(): Promise<ApiResponse<SectShopPayload>> {
  try {
    const response = await http.get<ApiResponse<SectShopPayload>>('/sect/shop')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<SectShopPayload>(error)
  }
}

/**
 * POST /sect/shop/buy
 *
 * @param body - item_id
 */
export async function buySectShop(body: {
  item_id: string
}): Promise<ApiResponse<SectShopBuyResult>> {
  try {
    const response = await http.post<ApiResponse<SectShopBuyResult>>(
      '/sect/shop/buy',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<SectShopBuyResult>(error)
  }
}

/** GET /sect/soul-lamps */
export async function fetchSoulLamps(): Promise<ApiResponse<SoulLampListPayload>> {
  try {
    const response = await http.get<ApiResponse<SoulLampListPayload>>(
      '/sect/soul-lamps',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<SoulLampListPayload>(error)
  }
}

/** GET /sect/exchange/catalog */
export async function fetchExchangeCatalog(): Promise<
  ApiResponse<ExchangeCatalogPayload>
> {
  try {
    const response = await http.get<ApiResponse<ExchangeCatalogPayload>>(
      '/sect/exchange/catalog',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<ExchangeCatalogPayload>(error)
  }
}

/**
 * POST /sect/exchange/pet — 宗门兑宠。
 *
 * @param body - species_id
 */
export async function exchangeSectPet(body: {
  species_id: string
}): Promise<ApiResponse<SectPetExchangeResult>> {
  try {
    const response = await http.post<ApiResponse<SectPetExchangeResult>>(
      '/sect/exchange/pet',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<SectPetExchangeResult>(error)
  }
}
