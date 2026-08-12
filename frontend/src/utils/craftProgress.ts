/**
 * 工坊本地进度预测（仅 UI 展示；权威完成以服务端 finish_at / status=ready 为准）。
 */

/**
 * 计算 running 任务进度 0～1。
 *
 * 参数:
 * - startedAt: ISO 开工时间
 * - finishAt: ISO 预计完成时间
 * - nowMs: 当前毫秒时间戳
 */
export function craftProgressRatio(
  startedAt: string,
  finishAt: string,
  nowMs: number = Date.now(),
): number {
  const start = Date.parse(startedAt)
  const finish = Date.parse(finishAt)
  if (!Number.isFinite(start) || !Number.isFinite(finish) || finish <= start) {
    return 0
  }
  const ratio = (nowMs - start) / (finish - start)
  return Math.max(0, Math.min(1, ratio))
}
