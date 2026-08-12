/**
 * M5 世界环境 API：calendar / weather / env。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type {
  WorldCalendarPublic,
  WorldEnvPublic,
  WorldWeatherPublic,
} from '../types/world'

/** GET /world/calendar */
export async function fetchCalendar(): Promise<ApiResponse<WorldCalendarPublic>> {
  try {
    const response = await http.get<ApiResponse<WorldCalendarPublic>>('/world/calendar')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<WorldCalendarPublic>(error)
  }
}

/** GET /world/weather */
export async function fetchWeather(): Promise<ApiResponse<WorldWeatherPublic>> {
  try {
    const response = await http.get<ApiResponse<WorldWeatherPublic>>('/world/weather')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<WorldWeatherPublic>(error)
  }
}

/** GET /world/env（聚合 + 行为提示） */
export async function fetchWorldEnv(): Promise<ApiResponse<WorldEnvPublic>> {
  try {
    const response = await http.get<ApiResponse<WorldEnvPublic>>('/world/env')
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<WorldEnvPublic>(error)
  }
}
