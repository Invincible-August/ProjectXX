/**
 * 待引渡本地倒计时格式化。
 */

/**
 * 将截止时间转为剩余毫秒；已过期为 0。
 *
 * @param deadlineAt - ISO 截止时间
 * @param nowMs - 当前毫秒
 */
export function ferryRemainMs(
  deadlineAt: string | null | undefined,
  nowMs: number = Date.now(),
): number {
  if (!deadlineAt) return 0
  const target = Date.parse(deadlineAt)
  if (!Number.isFinite(target)) return 0
  return Math.max(0, target - nowMs)
}

/**
 * 格式化为 H:MM:SS 或 M:SS（不足一小时省略小时）。
 *
 * @param remainMs - 剩余毫秒
 */
export function formatFerryCountdown(remainMs: number): string {
  const totalSec = Math.max(0, Math.floor(remainMs / 1000))
  const hours = Math.floor(totalSec / 3600)
  const minutes = Math.floor((totalSec % 3600) / 60)
  const seconds = totalSec % 60
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  }
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

/**
 * 是否已到期（前端应 refresh，不可幻想自救成功）。
 *
 * @param deadlineAt - ISO 截止时间
 * @param nowMs - 当前毫秒
 */
export function isFerryExpired(
  deadlineAt: string | null | undefined,
  nowMs: number = Date.now(),
): boolean {
  return ferryRemainMs(deadlineAt, nowMs) <= 0
}
