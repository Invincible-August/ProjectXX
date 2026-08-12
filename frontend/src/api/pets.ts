/**
 * M4/N4 ?? API?
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  PetCatalogPayload,
  PetDuelState,
  PetHatchState,
  PetCaptureResult,
  PetEncounterPublic,
  PetExplorePreview,
  PetPublic,
} from '../types/pets'

/** GET /pets */
export async function fetchPets(): Promise<
  ApiResponse<{ pets: PetPublic[]; hold_cap?: number }>
> {
  try {
    const response = await http.get<ApiResponse<{ pets: PetPublic[]; hold_cap?: number }>>(
      '/pets',
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{ pets: PetPublic[]; hold_cap?: number }>(error)
  }
}

/** GET /pets/catalog */
export async function fetchPetCatalog(): Promise<ApiResponse<PetCatalogPayload>> {
  try {
    const response = await http.get<ApiResponse<PetCatalogPayload>>('/pets/catalog')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<PetCatalogPayload>(error)
  }
}

/** POST /pets/capture_test ? ?? species_id ???????? */
export async function captureTestPet(body?: {
  species_id?: string | null
}): Promise<
  ApiResponse<{ id: number; species_id: string; grade?: number; pet?: PetPublic }>
> {
  try {
    const payload =
      body?.species_id != null && String(body.species_id).trim() !== ''
        ? { species_id: body.species_id }
        : { species_id: null }
    const response = await http.post<
      ApiResponse<{ id: number; species_id: string; grade?: number; pet?: PetPublic }>
    >('/pets/capture_test', payload)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{
      id: number
      species_id: string
      grade?: number
      pet?: PetPublic
    }>(error)
  }
}

/** POST /pets/{id}/upgrade */
export async function upgradePet(
  petId: number,
): Promise<ApiResponse<{ id: number; level: number; stats?: PetPublic['stats']; pet?: PetPublic }>> {
  try {
    const response = await http.post<
      ApiResponse<{ id: number; level: number; stats?: PetPublic['stats']; pet?: PetPublic }>
    >(`/pets/${petId}/upgrade`)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{
      id: number
      level: number
      stats?: PetPublic['stats']
      pet?: PetPublic
    }>(error)
  }
}

/** POST /pets/{id}/grade-up */
export async function gradeUpPet(
  petId: number,
): Promise<
  ApiResponse<{
    id: number
    grade: number
    spirit_stones_spent: number
    spirit_stones: number
    pet?: PetPublic
  }>
> {
  try {
    const response = await http.post<
      ApiResponse<{
        id: number
        grade: number
        spirit_stones_spent: number
        spirit_stones: number
        pet?: PetPublic
      }>
    >(`/pets/${petId}/grade-up`)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{
      id: number
      grade: number
      spirit_stones_spent: number
      spirit_stones: number
      pet?: PetPublic
    }>(error)
  }
}

/** POST /pets/{id}/affix/reroll-value */
export async function rerollPetAffixValue(
  petId: number,
  slotIndex: number,
): Promise<
  ApiResponse<{
    id: number
    slot_index: number
    spirit_stones_spent: number
    spirit_stones: number
    pet?: PetPublic
  }>
> {
  try {
    const response = await http.post<
      ApiResponse<{
        id: number
        slot_index: number
        spirit_stones_spent: number
        spirit_stones: number
        pet?: PetPublic
      }>
    >(`/pets/${petId}/affix/reroll-value`, { slot_index: slotIndex })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{
      id: number
      slot_index: number
      spirit_stones_spent: number
      spirit_stones: number
      pet?: PetPublic
    }>(error)
  }
}

/** POST /pets/{id}/feed (PET-D04) */
export async function feedPet(
  petId: number,
  itemId: string,
  quantity = 1,
): Promise<
  ApiResponse<{
    id: number
    item_id: string
    quantity: number
    times_fed?: number
    total_used?: number
    total_cap?: number
    pet?: PetPublic
  }>
> {
  try {
    const response = await http.post<
      ApiResponse<{
        id: number
        item_id: string
        quantity: number
        times_fed?: number
        total_used?: number
        total_cap?: number
        pet?: PetPublic
      }>
    >(`/pets/${petId}/feed`, { item_id: itemId, quantity })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{
      id: number
      item_id: string
      quantity: number
      times_fed?: number
      total_used?: number
      total_cap?: number
      pet?: PetPublic
    }>(error)
  }
}

/** POST /pets/sect/affix/reroll-type (PET-D06) */
export async function rerollPetAffixType(
  petId: number,
  slotIndex: number,
): Promise<
  ApiResponse<{
    id: number
    slot_index: number
    spirit_stones_spent: number
    spirit_stones: number
    type_reroll_count?: number
    pet?: PetPublic
  }>
> {
  try {
    const response = await http.post<
      ApiResponse<{
        id: number
        slot_index: number
        spirit_stones_spent: number
        spirit_stones: number
        type_reroll_count?: number
        pet?: PetPublic
      }>
    >('/pets/sect/affix/reroll-type', { pet_id: petId, slot_index: slotIndex })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{
      id: number
      slot_index: number
      spirit_stones_spent: number
      spirit_stones: number
      type_reroll_count?: number
      pet?: PetPublic
    }>(error)
  }
}

/** POST /pets/{id}/skills/equip */
export async function equipPetSkills(
  petId: number,
  equipped: Array<string | null>,
): Promise<ApiResponse<{ id: number; equipped_ids?: Array<string | null>; pet?: PetPublic }>> {
  try {
    const response = await http.post<
      ApiResponse<{ id: number; equipped_ids?: Array<string | null>; pet?: PetPublic }>
    >(`/pets/${petId}/skills/equip`, { equipped })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{
      id: number
      equipped_ids?: Array<string | null>
      pet?: PetPublic
    }>(error)
  }
}

/** POST /pets/{id}/skills/learn */
export async function learnPetSkillFromPool(
  petId: number,
  skillId: string,
): Promise<ApiResponse<{ id: number; learned_skill_id?: string; pet?: PetPublic }>> {
  try {
    const response = await http.post<
      ApiResponse<{ id: number; learned_skill_id?: string; pet?: PetPublic }>
    >(`/pets/${petId}/skills/learn`, { skill_id: skillId })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{
      id: number
      learned_skill_id?: string
      pet?: PetPublic
    }>(error)
  }
}

/** POST /pets/{id}/skills/learn_book */
export async function learnPetSkillFromBook(
  petId: number,
  bookId: string,
): Promise<
  ApiResponse<{ id: number; book_id?: string; learned_skill_id?: string; pet?: PetPublic }>
> {
  try {
    const response = await http.post<
      ApiResponse<{ id: number; book_id?: string; learned_skill_id?: string; pet?: PetPublic }>
    >(`/pets/${petId}/skills/learn_book`, { book_id: bookId })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{
      id: number
      book_id?: string
      learned_skill_id?: string
      pet?: PetPublic
    }>(error)
  }
}

/** PATCH /pets/{id} */
export async function patchPet(
  petId: number,
  body: { nickname?: string; is_deploy_preferred?: boolean },
): Promise<
  ApiResponse<{ id: number; nickname?: string | null; is_deploy_preferred?: boolean }>
> {
  try {
    const response = await http.patch<
      ApiResponse<{ id: number; nickname?: string | null; is_deploy_preferred?: boolean }>
    >(`/pets/${petId}`, body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{
      id: number
      nickname?: string | null
      is_deploy_preferred?: boolean
    }>(error)
  }
}

/** POST /pets/duel/npc/start */
export async function startPetDuelNpc(body: {
  pet_id: number
  npc_id?: string | null
  seed?: number | null
}): Promise<
  ApiResponse<{ duel_id: string; npc_id: string; seed: number; state: PetDuelState }>
> {
  try {
    const response = await http.post<
      ApiResponse<{ duel_id: string; npc_id: string; seed: number; state: PetDuelState }>
    >('/pets/duel/npc/start', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{
      duel_id: string
      npc_id: string
      seed: number
      state: PetDuelState
    }>(error)
  }
}

/** POST /pets/duel/{id}/turn */
export async function turnPetDuel(
  duelId: string,
  skillId: string | null,
): Promise<
  ApiResponse<{
    state: PetDuelState
    turn_events: Array<Record<string, unknown>>
    finished: boolean
    winner: string | null
  }>
> {
  try {
    const response = await http.post<
      ApiResponse<{
        state: PetDuelState
        turn_events: Array<Record<string, unknown>>
        finished: boolean
        winner: string | null
      }>
    >(`/pets/duel/${duelId}/turn`, { skill_id: skillId })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{
      state: PetDuelState
      turn_events: Array<Record<string, unknown>>
      finished: boolean
      winner: string | null
    }>(error)
  }
}

/** POST /pets/duel/npc/auto */
export async function autoPetDuelNpc(body: {
  pet_id: number
  npc_id?: string | null
  seed?: number | null
}): Promise<
  ApiResponse<{
    report: {
      winner: string | null
      rounds: number
      seed: number
      events: Array<Record<string, unknown>>
    }
    state: PetDuelState
  }>
> {
  try {
    const response = await http.post<
      ApiResponse<{
        report: {
          winner: string | null
          rounds: number
          seed: number
          events: Array<Record<string, unknown>>
        }
        state: PetDuelState
      }>
    >('/pets/duel/npc/auto', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{
      report: {
        winner: string | null
        rounds: number
        seed: number
        events: Array<Record<string, unknown>>
      }
      state: PetDuelState
    }>(error)
  }
}

/** GET /pets/hatch (N5) */
export async function fetchPetHatch(): Promise<ApiResponse<PetHatchState>> {
  try {
    const response = await http.get<ApiResponse<PetHatchState>>('/pets/hatch')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<PetHatchState>(error)
  }
}

/** POST /pets/hatch/start */
export async function startPetHatch(
  eggItemId: string,
): Promise<ApiResponse<{ job: PetHatchState['jobs'][number]; spirit_stones?: number }>> {
  try {
    const response = await http.post<
      ApiResponse<{ job: PetHatchState['jobs'][number]; spirit_stones?: number }>
    >('/pets/hatch/start', { egg_item_id: eggItemId })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{
      job: PetHatchState['jobs'][number]
      spirit_stones?: number
    }>(error)
  }
}

/** POST /pets/hatch/{id}/claim */
export async function claimPetHatch(
  jobId: number,
): Promise<ApiResponse<{ pet?: PetPublic; id?: number; job?: PetHatchState['jobs'][number] }>> {
  try {
    const response = await http.post<
      ApiResponse<{ pet?: PetPublic; id?: number; job?: PetHatchState['jobs'][number] }>
    >(`/pets/hatch/${jobId}/claim`)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{
      pet?: PetPublic
      id?: number
      job?: PetHatchState['jobs'][number]
    }>(error)
  }
}

/** GET /pets/explore/preview (M4-D04c) */
export async function fetchPetExplorePreview(
  regionId = 'default',
): Promise<ApiResponse<PetExplorePreview>> {
  try {
    const response = await http.get<ApiResponse<PetExplorePreview>>('/pets/explore/preview', {
      params: { region_id: regionId },
    })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<PetExplorePreview>(error)
  }
}

/** POST /pets/explore/encounter */
export async function explorePetEncounter(body?: {
  region_id?: string
  seed?: number | null
}): Promise<ApiResponse<PetEncounterPublic>> {
  try {
    const response = await http.post<ApiResponse<PetEncounterPublic>>('/pets/explore/encounter', {
      region_id: body?.region_id ?? 'default',
      seed: body?.seed ?? null,
    })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<PetEncounterPublic>(error)
  }
}

/** POST /pets/explore/capture */
export async function explorePetCapture(body: {
  encounter_id: string
  seed?: number | null
}): Promise<ApiResponse<PetCaptureResult>> {
  try {
    const response = await http.post<ApiResponse<PetCaptureResult>>('/pets/explore/capture', {
      encounter_id: body.encounter_id,
      seed: body.seed ?? null,
    })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<PetCaptureResult>(error)
  }
}

/** POST /pets/explore/auto */
export async function explorePetAuto(body?: {
  region_id?: string
  seed?: number | null
}): Promise<
  ApiResponse<{
    rolls: PetEncounterPublic[]
    capture: PetCaptureResult | null
    seed: number
    auto: boolean
  }>
> {
  try {
    const response = await http.post<
      ApiResponse<{
        rolls: PetEncounterPublic[]
        capture: PetCaptureResult | null
        seed: number
        auto: boolean
      }>
    >('/pets/explore/auto', {
      region_id: body?.region_id ?? 'default',
      seed: body?.seed ?? null,
    })
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{
      rolls: PetEncounterPublic[]
      capture: PetCaptureResult | null
      seed: number
      auto: boolean
    }>(error)
  }
}
