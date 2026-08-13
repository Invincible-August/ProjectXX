/**
 * M7 L6 师徒 HTTP API。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type { MentorMePayload } from '../types/mentor'

export async function fetchMentorMe(): Promise<ApiResponse<MentorMePayload>> {
  try {
    const response = await http.get<ApiResponse<MentorMePayload>>('/mentor/me')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<MentorMePayload>(error)
  }
}

export async function applyMentor(body: {
  target_name?: string | null
  target_character_id?: number | null
  intent: 'apprentice' | 'master'
}): Promise<ApiResponse<{ message?: string; bond_id?: number }>> {
  try {
    const response = await http.post<ApiResponse<{ message?: string; bond_id?: number }>>(
      '/mentor/apply',
      body,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function acceptMentor(bondId: number): Promise<ApiResponse<{ message?: string }>> {
  try {
    const response = await http.post<ApiResponse<{ message?: string }>>(
      `/mentor/${bondId}/accept`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function rejectMentor(bondId: number): Promise<ApiResponse<{ message?: string }>> {
  try {
    const response = await http.post<ApiResponse<{ message?: string }>>(
      `/mentor/${bondId}/reject`,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function teachLesson(body: {
  kind: 'dao' | 'craft' | 'technique'
  resource?: 'spirit' | 'body' | null
  target_id?: string | null
}): Promise<ApiResponse<{ message?: string }>> {
  try {
    const response = await http.post<ApiResponse<{ message?: string }>>('/mentor/lesson', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function teachItem(body: {
  item_kind: 'technique' | 'recipe'
  item_id: string
}): Promise<ApiResponse<{ message?: string }>> {
  try {
    const response = await http.post<ApiResponse<{ message?: string }>>('/mentor/teach', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function studyTechnique(body: {
  technique_id: string
}): Promise<ApiResponse<{ message?: string }>> {
  try {
    const response = await http.post<ApiResponse<{ message?: string }>>('/mentor/study', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function setDirectDisciples(body: {
  apprentice_character_ids: number[]
}): Promise<
  ApiResponse<{ message?: string; log_lines?: string[]; appointed?: string[]; cleared?: string[] }>
> {
  try {
    const response = await http.post<
      ApiResponse<{
        message?: string
        log_lines?: string[]
        appointed?: string[]
        cleared?: string[]
      }>
    >('/mentor/direct', body)
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

/** @deprecated 兼容旧传功；等价传道·修为 */
export async function passCultivation(): Promise<ApiResponse<{ message?: string }>> {
  try {
    const response = await http.post<ApiResponse<{ message?: string }>>('/mentor/pass')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function graduateMentor(): Promise<ApiResponse<{ message?: string }>> {
  try {
    const response = await http.post<ApiResponse<{ message?: string }>>('/mentor/graduate')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}

export async function dissolveMentor(): Promise<ApiResponse<{ message?: string }>> {
  try {
    const response = await http.post<ApiResponse<{ message?: string }>>('/mentor/dissolve')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError(error)
  }
}
