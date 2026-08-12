/**
 * 炼体淬体 API（与修为突破分立）。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type { CharacterPublic } from '../types/character'

/** 淬体预览 */
export interface QuenchPreview {
  can_quench: boolean
  reason: string | null
  advance_type?: 'layer' | 'major' | string | null
  advance_type_label_zh?: string | null
  success_rate?: number
  fail_progress_keep_ratio?: number
  needs_tribulation?: boolean
  from_stage: string
  from_stage_name: string
  from_display?: string
  from_layer?: number
  to_stage: string | null
  to_stage_name: string | null
  to_display?: string | null
  to_layer?: number | null
  progress: number
  required: number
  character?: CharacterPublic
}

/** 淬体结果 */
export interface QuenchAttemptResult {
  success: boolean
  message: string
  advance_type?: string
  success_rate?: number
  from_stage?: string
  from_stage_name?: string
  from_display?: string
  to_stage?: string
  to_stage_name?: string
  to_display?: string
  needs_tribulation?: boolean
  character: CharacterPublic
}

/** GET /quench/preview */
export async function previewQuenchApi(): Promise<ApiResponse<QuenchPreview>> {
  try {
    const response = await http.get<ApiResponse<QuenchPreview>>('/quench/preview')
    return response.data
  } catch (error) {
    return envelopeFromAxiosError(error)
  }
}

/** POST /quench/attempt */
export async function attemptQuenchApi(): Promise<ApiResponse<QuenchAttemptResult>> {
  try {
    const response = await http.post<ApiResponse<QuenchAttemptResult>>(
      '/quench/attempt',
    )
    return response.data
  } catch (error) {
    return envelopeFromAxiosError(error)
  }
}
