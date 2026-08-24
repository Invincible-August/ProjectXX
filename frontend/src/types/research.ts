/**
 * Research types (M8 R2) — align with backend app.constants.research.
 */
export type ResearchKind = 'technique' | 'formation' | 'talisman'

export type ResearchPhase =
  | 'drafting'
  | 'previewed'
  | 'finalized'
  | 'cancelled'
  | 'expired'

export interface ResearchAffixPreview {
  id: string
  label_zh: string
  stats?: Record<string, number>
}

export interface ResearchSessionPublic {
  id: number
  kind: ResearchKind
  kind_label_zh: string
  phase: ResearchPhase
  phase_label_zh: string
  reroll_count: number
  dice?: {
    purpose: string
    roll: number | null
    label_zh: string
  }
  affix_previews: ResearchAffixPreview[]
  blueprint?: FormationBlueprintDraft | null
  effect_id?: string | null
  expires_at?: string | null
  private_content_id?: string | null
  private?: PrivateContentPublic
}

export interface PrivateContentPublic {
  id: string
  source: 'custom'
  source_label_zh: '自研'
  label_zh: string
  revision: number
  kind: ResearchKind
  track?: string
  stats?: Record<string, number>
  blueprint?: FormationBlueprintDraft
  effect_id?: string
  effect_label_zh?: string
}

export interface FormationBlueprintDraft {
  deploy: {
    mode: string
    cells: [number, number][] | number[][]
    add_cells?: [number, number][] | number[][]
    exclude_cells?: [number, number][] | number[][]
    allow_neutral?: boolean
    max_units?: number | null
  }
  terrain_layout?: Record<string, unknown>
  terrain: Array<{ x: number; y: number; type: string; subtype?: string }>
  force_shifts?: unknown[]
  environment?: { id: string } | null
  weather?: { id: string } | null
  effect?: { id: string } | null
}

export interface ResearchCatalog {
  schema_version: number
  kinds: Array<{ id: ResearchKind; label_zh: string; open: boolean }>
  technique: {
    label_zh: string
    help_zh: string
    allowed_materials: string[]
    min_materials: number
    spend: { cultivation_points: number; body_tempering_points: number }
    reroll: { max_rerolls: number; extra_materials: Array<{ item_id: string; quantity: number }> }
    affix_slots: number
  }
  affixes: Array<{ id: string; label_zh: string; help_zh: string; stats: Record<string, number> }>
  formation?: {
    label_zh: string
    help_zh: string
    allowed_materials: string[]
    min_materials: number
    spend: { cultivation_points: number; body_tempering_points: number }
    required_array_level: number
    allowed_deploy_modes: string[]
    default_deploy_mode: string
    terrain_layout: Record<string, unknown>
    max_force_shifts: number
  }
  talisman?: {
    label_zh: string
    help_zh: string
    allowed_materials: string[]
    min_materials: number
    spend: { cultivation_points: number; body_tempering_points: number }
    scribe: { paper_item_id: string; paper_per_copy: number; max_batch: number }
    preload_slots: number
    battle_enabled: boolean
    effects: Array<{ id: string; label_zh: string; help_zh: string; trigger: string }>
  }
}

export interface ResearchCreateRequest {
  kind: ResearchKind
  materials: Array<{ item_id: string; quantity: number }>
  spends: Record<string, number>
  effect_id?: string
}
