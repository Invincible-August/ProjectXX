/**
 * 右上角邀请/社交通知：点击整条提示跳转到对应页面。
 * 同一 dedupeKey 短窗内只弹一次，避免 invite+update 双推。
 */
import { ElNotification } from 'element-plus'
import type { RouteLocationRaw } from 'vue-router'
import router from '../router'

export type InviteNotifyType = 'success' | 'warning' | 'info' | 'error'

const recentKeys = new Map<string, number>()
const DEDUPE_MS = 4_000

function shouldSkipDedupe(key: string | undefined): boolean {
  if (!key) return false
  const now = Date.now()
  for (const [k, ts] of recentKeys) {
    if (now - ts > DEDUPE_MS) recentKeys.delete(k)
  }
  const prev = recentKeys.get(key)
  if (prev != null && now - prev < DEDUPE_MS) return true
  recentKeys.set(key, now)
  return false
}

/**
 * 弹出可点击通知并在点击后跳转。
 *
 * @param opts - 标题、文案、目标路由；可选跳转后回调与去重键
 */
export function notifyInviteJump(opts: {
  title: string
  message: string
  to: RouteLocationRaw
  type?: InviteNotifyType
  duration?: number
  /** 去重键，如 ``party:invite:12`` */
  dedupeKey?: string
  /** 先跳转，再后台刷新，避免点了却迟迟不跳 */
  afterNavigate?: () => void | Promise<void>
}): void {
  const message = String(opts.message || '').trim()
  if (!message) return
  if (shouldSkipDedupe(opts.dedupeKey)) return
  ElNotification({
    title: opts.title,
    message,
    type: opts.type || 'info',
    duration: opts.duration ?? 8_000,
    customClass: 'invite-jump-notify',
    onClick: () => {
      void router.push(opts.to).then(() => {
        if (opts.afterNavigate) {
          void opts.afterNavigate()
        }
      })
    },
  })
}
