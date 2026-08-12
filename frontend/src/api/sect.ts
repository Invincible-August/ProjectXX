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
 * @param body - name + 可选 motto
 */
export async function createSect(body: {
  name: string
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
