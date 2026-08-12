/**
 * 资源分配 API 类型（M2）。
 */
import type { CharacterPublic } from './character'

export type AllocateTargetType = 'realm' | 'technique'

export interface AllocateRequest {
  target_type: AllocateTargetType
  target_id?: string | null
  amount: number
}

export interface AllocateResult {
  allocated: number
  levels_gained: number
  message: string
  character: CharacterPublic
}
