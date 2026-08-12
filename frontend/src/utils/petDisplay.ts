/**
 * 灵宠展示名工具。
 */
import type { PetPublic } from '../types/pets'

/** 优先昵称，否则物种名。 */
export function petDisplayName(pet: Pick<PetPublic, 'nickname' | 'species_name' | 'species_id'>): string {
  return pet.nickname?.trim() || pet.species_name || pet.species_id
}
