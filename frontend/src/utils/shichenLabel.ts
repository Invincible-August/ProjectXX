/**
 * 六时中文标签与倒计时格式化。
 */
import type { ShichenId } from '../types/world'

/** 六时固定中文（与后端 label 兜底对齐） */
export const SHICHEN_LABELS: Record<ShichenId, string> = {
  dawn: '清晨',
  noon: '正午',
  afternoon: '晌午',
  dusk: '傍晚',
  night: '半夜',
  late_night: '深夜',
}

/**
 * 解析时辰展示名。
 *
 * @param id - 时辰 id
 * @param serverLabel - 服务端下发 label（优先）
 */
export function shichenLabel(
  id: ShichenId | string | null | undefined,
  serverLabel?: string | null,
): string {
  if (serverLabel) return serverLabel
  if (id && id in SHICHEN_LABELS) {
    return SHICHEN_LABELS[id as ShichenId]
  }
  // §0.0.2：未知时辰不得裸出英文 id
  return id ? `未知(${id})` : '—'
}

/**
 * 距下一时的倒计时文案（m:ss）；已过期返回 0:00。
 *
 * @param nextShichenAt - ISO 时间
 * @param nowMs - 当前毫秒时间戳
 */
export function formatShichenCountdown(
  nextShichenAt: string | null | undefined,
  nowMs: number = Date.now(),
): string {
  if (!nextShichenAt) return '—'
  const target = Date.parse(nextShichenAt)
  if (!Number.isFinite(target)) return '—'
  const remainSec = Math.max(0, Math.floor((target - nowMs) / 1000))
  const minutes = Math.floor(remainSec / 60)
  const seconds = remainSec % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}
