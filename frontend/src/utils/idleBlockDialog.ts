/**
 * 修炼占用：点开战/突破/工坊等时再弹框，不在修炼区常驻长文案。
 */
import { ElMessageBox } from 'element-plus'
import type { CharacterPublic } from '../types/character'
import { isIdleBusyDirection } from './idlePredict'

export type IdleBlockActor = 'main' | 'avatar' | 'either'

function avatarIdleDirection(character: CharacterPublic): string {
  return String(
    character.dual_idle_preview?.avatar_idle_direction ??
      character.avatar_summary?.idle_direction ??
      'none',
  )
}

/**
 * 若当前主体正在修炼/采矿，返回弹框文案；否则 null。
 *
 * @param character - 权威角色
 * @param action - 动作短名，如「突破」「开战」
 * @param actor - 检查本体 / 化身 / 任一线程
 */
export function idleBlockMessage(
  character: CharacterPublic | null | undefined,
  action: string,
  actor: IdleBlockActor = 'either',
): string | null {
  if (!character) return null
  const mainDir = String(character.idle_direction || 'none')
  const avDir = avatarIdleDirection(character)
  const mainBusy = isIdleBusyDirection(mainDir)
  const avBusy = isIdleBusyDirection(avDir)
  const checkMain = actor === 'main' || actor === 'either'
  const checkAv = actor === 'avatar' || actor === 'either'
  if (checkMain && mainBusy) {
    if (mainDir === 'sect_mining') {
      return `采矿中无法进行${action}，请先结束采矿`
    }
    return `修炼中无法进行${action}，请先停止修炼`
  }
  if (checkAv && avBusy) {
    if (avDir === 'sect_mining') {
      return `化身采矿中无法进行${action}，请先结束化身采矿`
    }
    return `化身修炼中无法进行${action}，请先停止化身修炼`
  }
  return null
}

/**
 * 占用则弹出提示并返回 true；可继续则返回 false。
 *
 * @param character - 权威角色
 * @param action - 动作短名
 * @param actor - 检查哪条线程
 */
export async function alertIfIdleBlocked(
  character: CharacterPublic | null | undefined,
  action: string,
  actor: IdleBlockActor = 'either',
): Promise<boolean> {
  const message = idleBlockMessage(character, action, actor)
  if (!message) return false
  try {
    await ElMessageBox.alert(message, '无法进行', {
      confirmButtonText: '知道了',
      type: 'warning',
    })
  } catch {
    // 点遮罩关闭仍视为已提示
  }
  return true
}
