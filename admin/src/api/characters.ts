/** 玩家角色管理 API。 */
import { http, unwrap } from './http'

export interface FieldMetaDto {
  key: string
  label_zh: string
  help_zh: string
  value_type: string
}

export interface CharacterOpsSchema {
  module_id: string
  title_zh: string
  description_zh: string
  page_sizes: number[]
  default_page_size: number
  status_options: { value: string; label_zh: string }[]
  craft_branches: { value: string; label_zh: string }[]
  currencies: { key: string; ledger_key: string; label_zh: string; help_zh: string }[]
  base_attr_fields: FieldMetaDto[]
  forms: { grant_item: FieldMetaDto[] }
  note_zh: string
}

export interface CharacterListRow {
  id: number
  name: string
  user_db_id: number
  user_id: string
  major_realm: string
  major_realm_name: string
  realm_stage: number
  realm_display: string
  body_temper_stage: string
  body_temper_layer: number
  status: string
  status_label_zh: string
  spirit_stones: number
  cultivation_points: number
  is_active: boolean
}

export interface CharacterDetail extends CharacterListRow {
  email: string | null
  phone: string | null
  realm_progress: number
  body_tempering_points: number
  body_temper_progress: number
  body_temper_display: string | null
  crafting_exp: number
  stamina: number
  fate_luck_readonly: number
  demonic_nature: number
  base_attrs: { key: string; label_zh: string; value: number }[]
  craft_levels: { branch: string; label_zh: string; level: number }[]
  currencies: { key: string; label_zh: string; help_zh: string; amount: number }[]
  techniques: {
    id: number
    technique_id: string
    name: string
    level: number
    track: string | null
  }[]
  inventory: {
    items: InventoryItemRow[]
    normal_items: InventoryItemRow[]
    reincarnation_items: InventoryItemRow[]
  }
  recipes_by_branch: Record<
    string,
    { id: number; recipe_id: string; name: string; branch: string; source: string }[]
  >
  constitution: {
    items: {
      id: number
      def_id: string
      quality: string
      grade: string
      kind: string
      is_equipped: boolean
    }[]
    slots: {
      id: number
      slot_type: string
      slot_index: number
      item_instance_id: number | null
    }[]
  }
}

export interface InventoryItemRow {
  id: number
  item_uid: string
  item_type: string
  item_id: string
  name: string
  quantity: number
  bag_kind: string
  meta: Record<string, unknown> | null
  unique: boolean
  max_stack: number
}

export interface CharacterListResult {
  items: CharacterListRow[]
  total: number
  page: number
  page_size: number
}

export async function fetchCharacterOpsSchema() {
  return unwrap<CharacterOpsSchema>(http.get('/ops/characters/schema'))
}

export async function fetchCharacters(params: {
  q?: string
  page?: number
  page_size?: number
  user_db_id?: number
}) {
  return unwrap<CharacterListResult>(
    http.get('/ops/characters', {
      params: {
        q: params.q || undefined,
        page: params.page ?? 1,
        page_size: params.page_size ?? 20,
        user_db_id: params.user_db_id,
      },
    }),
  )
}

export async function fetchCharacterDetail(id: number) {
  return unwrap<CharacterDetail>(http.get(`/ops/characters/${id}`))
}

export async function softDeleteCharacter(id: number, note?: string) {
  return unwrap<CharacterDetail>(
    http.post(`/ops/characters/${id}/soft-delete`, { note: note || null }),
  )
}

export async function killCharacter(id: number, note?: string) {
  return unwrap<CharacterDetail>(http.post(`/ops/characters/${id}/kill`, { note: note || null }))
}

export async function reincarnateCharacter(id: number, note?: string) {
  return unwrap<CharacterDetail>(
    http.post(`/ops/characters/${id}/reincarnate`, { note: note || null }),
  )
}

export async function breakthroughCultivation(id: number) {
  return unwrap<CharacterDetail>(http.post(`/ops/characters/${id}/breakthrough/cultivation`, {}))
}

export async function breakthroughBody(id: number) {
  return unwrap<CharacterDetail>(http.post(`/ops/characters/${id}/breakthrough/body`, {}))
}

export async function grantCharacterItem(
  id: number,
  body: { item_id: string; quantity: number; note?: string },
) {
  return unwrap<CharacterDetail>(http.post(`/ops/characters/${id}/grant-item`, body))
}

export async function updateCharacterBaseAttrs(id: number, attrs: Record<string, number>) {
  return unwrap<CharacterDetail>(http.post(`/ops/characters/${id}/base-attrs`, { attrs }))
}

export async function updateCharacterStatus(id: number, status: string) {
  return unwrap<CharacterDetail>(http.post(`/ops/characters/${id}/status`, { status }))
}

export async function updateCharacterInventory(
  id: number,
  itemRowId: number,
  body: { quantity?: number; meta?: Record<string, unknown>; delete?: boolean },
) {
  return unwrap<CharacterDetail>(
    http.post(`/ops/characters/${id}/inventory/${itemRowId}`, body),
  )
}

export async function updateTechniqueLevel(id: number, techniqueId: string, level: number) {
  return unwrap<CharacterDetail>(
    http.post(`/ops/characters/${id}/techniques/${encodeURIComponent(techniqueId)}`, { level }),
  )
}

export async function learnTechnique(id: number, techniqueId: string, level = 0) {
  return unwrap<CharacterDetail>(
    http.post(`/ops/characters/${id}/techniques/learn`, {
      technique_id: techniqueId,
      level,
    }),
  )
}

export async function forgetTechnique(id: number, techniqueId: string) {
  return unwrap<CharacterDetail>(
    http.post(
      `/ops/characters/${id}/techniques/${encodeURIComponent(techniqueId)}/forget`,
      {},
    ),
  )
}

export async function updateCharacterRealm(
  id: number,
  body: {
    track: 'cultivation' | 'body'
    major?: string
    stage?: number
    progress?: number
    pool_points?: number
  },
) {
  return unwrap<CharacterDetail>(http.post(`/ops/characters/${id}/realm`, body))
}

export async function updateCraftLevels(id: number, levels: Record<string, number>) {
  return unwrap<CharacterDetail>(http.post(`/ops/characters/${id}/craft-levels`, { levels }))
}

export async function learnRecipe(id: number, recipeId: string) {
  return unwrap<CharacterDetail>(
    http.post(`/ops/characters/${id}/recipes/learn`, { recipe_id: recipeId }),
  )
}

export async function forgetRecipe(id: number, recipeId: string) {
  return unwrap<CharacterDetail>(
    http.post(`/ops/characters/${id}/recipes/${encodeURIComponent(recipeId)}/forget`, {}),
  )
}

export async function updateCharacterCurrencies(id: number, amounts: Record<string, number>) {
  return unwrap<CharacterDetail>(http.post(`/ops/characters/${id}/currencies`, { amounts }))
}
