/**
 * 布阵 / 棋盘 / 快照 类型（M3）。
 *
 * 坐标口径：左下角 (0,0)，x 向右、y 向上；预设一律存进攻方视角。
 */

/** 棋盘坐标 */
export interface BoardCoord {
  x: number
  y: number
}

/** 单个棋子的占位（进攻方视角） */
export interface UnitPlacement {
  unit_uid: string
  unit_kind: string
  x: number
  y: number
  /** M4：灵宠 / 化身 / 真傀儡持有物 id；试炼木傀可省略 */
  ref_id?: number
}

/** 棋盘只读元数据（GET /formation/board-meta） */
export interface BoardMeta {
  size: number
  zones: {
    own_x: number[]
    neutral_x: number[]
    enemy_x: number[]
  }
  default_deploy: {
    x_min: number
    x_max: number
    y_min: number
    y_max: number
  }
  default_deploy_cells: [number, number][]
  default_max_units: number
  default_anchor_unit: BoardCoord
  mirror_rule: string
  unit_kinds: Record<
    string,
    { unique: boolean; required: boolean; enabled: boolean }
  >
}

/** 一个布阵预设槽 */
export interface FormationPreset {
  slot: number
  name: string
  role: 'attack' | 'defense' | 'temp' | string
  formation_id: string
  units: UnitPlacement[]
  updated_at: string | null
}

/** 阵法地形格（编辑器预览用） */
export interface FormationTerrainCell {
  x: number
  y: number
  type: 'obstacle' | 'ravine' | 'seal' | string
  subtype: string
}

/** 阵法部署契约（与服务端 deploy 对齐） */
export interface FormationDeployConfig {
  mode: 'default' | 'fixed' | 'free_own' | 'mask' | string
  max_units?: number | null
  cells: [number, number][]
  add_cells: [number, number][]
  exclude_cells: [number, number][]
  allow_neutral: boolean
}

/** 开战强制移位预览 */
export interface ForceShiftPreview {
  from: [number, number]
  to: [number, number]
  only_kinds?: string[]
}

/** 阵法摘要（列表项） */
export interface FormationInfo {
  formation_id: string
  name: string
  level: number
  unlocked: boolean
  /** M4：解锁所需阵法钻研等级 */
  required_array_level?: number
  terrain: FormationTerrainCell[]
  /** M3-D08：部署契约 */
  deploy?: FormationDeployConfig
  /** 服务端解析后的有效可部署格（高亮权威源） */
  effective_deploy_cells?: [number, number][]
  /** 开战移位预览 */
  force_shifts?: ForceShiftPreview[]
  /** 阵法额外上阵上限（可空） */
  max_units_formation?: number | null
  /** 服务端权威：min(境界, 格数, 阵法) */
  max_units_effective?: number
}

/** 可上阵棋子（Bench 项） */
export interface BenchUnit {
  unit_uid: string
  unit_kind: 'main' | 'avatar' | 'pet' | 'puppet' | string
  /** 展示名（兼容旧字段 name） */
  display_name?: string
  name: string
  enabled: boolean
  ref_id?: number
  disabled_reason?: string
  stats_preview?: { atk: number; hp: number; speed: number }
}

/** GET /formation/presets 响应 */
export interface PresetsPayload {
  presets: FormationPreset[]
  formations: FormationInfo[]
  bench: BenchUnit[]
  max_units: number
}

/** 防守快照 payload（服务端冻结内容） */
export interface DefenseSnapshotPayload {
  schema_version: number
  character_id: number
  dao_name: string
  realm: { major: string; stage: number; label: string }
  breakthrough_grade: string
  formation_id: string
  units: (UnitPlacement & {
    atk: number
    hp: number
    speed: number
    attack_range: number
    attack_kind: string
    can_fly: boolean
    name: string
  })[]
  content_hash: string
  created_at: string
}

/** GET /snapshot/defense/me 响应 */
export interface MySnapshotPayload {
  snapshot: DefenseSnapshotPayload
  updated_at: string | null
  cooldown_remaining_seconds: number
}

/** GET /snapshot/defense/{id} 响应（攻打前预览） */
export interface SnapshotPreviewPayload {
  character_id: number
  dao_name: string
  realm: { major: string; stage: number; label: string }
  breakthrough_grade: string
  formation_id: string
  /** 阵法中文名（§0.0.2） */
  formation_name?: string
  units: DefenseSnapshotPayload['units']
  updated_at: string | null
}
