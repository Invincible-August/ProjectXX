/**
 * 天气图标 / 文案映射（轻量占位，非终局美术）。
 */
import type { WorldWeatherId } from '../types/world'

/** 天气 emoji 占位 */
export const WEATHER_ICONS: Record<WorldWeatherId, string> = {
  clear: '☀️',
  overcast: '☁️',
  rain: '🌧️',
  hurricane: '🌀',
  storm: '🌬️',
  thunderstorm: '⛈️',
}

/** 天气中文兜底 */
export const WEATHER_LABELS: Record<WorldWeatherId, string> = {
  clear: '晴',
  overcast: '阴',
  rain: '雨',
  hurricane: '飓风',
  storm: '风暴',
  thunderstorm: '雷暴',
}

/**
 * 从可能是字符串或嵌套对象的天气字段中取出 id。
 *
 * @param weather - id 或 `{ weather_id / weather / label }`
 */
export function resolveWeatherId(
  weather: WorldWeatherId | string | Record<string, unknown> | null | undefined,
): string | null {
  if (weather == null) return null
  if (typeof weather === 'string') return weather
  if (typeof weather === 'object') {
    const id =
      weather.weather_id ??
      weather.display_weather_id ??
      weather.weather ??
      weather.id
    return typeof id === 'string' ? id : null
  }
  return null
}

/**
 * 从嵌套天气对象取 label。
 *
 * @param weather - id 或对象
 * @param serverLabel - 显式服务端文案
 */
export function resolveWeatherServerLabel(
  weather: WorldWeatherId | string | Record<string, unknown> | null | undefined,
  serverLabel?: string | null,
): string | null {
  if (serverLabel) return serverLabel
  if (weather && typeof weather === 'object') {
    const label = weather.weather_label ?? weather.label
    return typeof label === 'string' ? label : null
  }
  return null
}

/**
 * 天气图标字符。
 *
 * @param weather - 天气 id 或嵌套对象
 */
export function weatherIcon(
  weather: WorldWeatherId | string | Record<string, unknown> | null | undefined,
): string {
  const id = resolveWeatherId(weather)
  if (id && id in WEATHER_ICONS) {
    return WEATHER_ICONS[id as WorldWeatherId]
  }
  if (id === 'tribulation_cloud') return '🌩️'
  return '🌫️'
}

/**
 * 天气展示名（绝不把对象直接 String 成 [object Object]）。
 *
 * @param weather - 天气 id 或嵌套对象
 * @param serverLabel - 服务端 label（优先）
 */
export function weatherLabel(
  weather: WorldWeatherId | string | Record<string, unknown> | null | undefined,
  serverLabel?: string | null,
): string {
  const fromObj = resolveWeatherServerLabel(weather, serverLabel)
  if (fromObj) return fromObj
  const id = resolveWeatherId(weather)
  if (id && id in WEATHER_LABELS) {
    return WEATHER_LABELS[id as WorldWeatherId]
  }
  if (id === 'tribulation_cloud') return '劫云'
  // §0.0.2：未知天气不得把英文 id 当正文
  return id ? `未知(${id})` : '—'
}
