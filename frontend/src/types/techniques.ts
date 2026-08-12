/**
 * 功法 API 类型（M2）。
 */

export interface TechniqueItem {
  id: string
  name: string
  track: string
  level: number
  max_level: number
  next_cost?: number | null
  cost_next?: number | null
}

export interface TechniquesMeData {
  items: TechniqueItem[]
}
