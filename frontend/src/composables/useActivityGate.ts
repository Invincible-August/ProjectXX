/**
 * 活动互斥前端门禁：读 CharacterPublic.activity，缺省时本地推导。
 */
import { computed } from 'vue'
import { useCharacterStore } from '../stores/character'
import type { ActivitySnapshot } from '../types/activity'
import { isIdleBusyDirection } from '../utils/idlePredict'

/**
 * 本地兜底推导活动快照（服务端字段缺失时）。
 *
 * @returns ActivitySnapshot
 */
function deriveLocalActivity(): ActivitySnapshot {
  const ch = useCharacterStore().character
  const status = ch?.status ?? 'normal'
  const idle = ch?.idle_direction ?? 'none'
  const craftRunning = ch?.craft_jobs_summary?.running ?? 0
  const productive = isIdleBusyDirection(idle)

  let mode: ActivitySnapshot['mode'] = 'free'
  let modeLabel = '空闲'
  if (status === 'tribulation') {
    mode = 'tribulation'
    modeLabel = '渡劫中'
  } else if (status === 'awaiting_ferry') {
    mode = 'awaiting_ferry'
    modeLabel = '待引渡'
  } else if (status === 'reincarnating') {
    mode = 'reincarnating'
    modeLabel = '轮回中'
  } else if (status === 'breaking_through') {
    mode = 'breaking_through'
    modeLabel = '进阶中'
  } else if (productive) {
    mode = 'idle'
    modeLabel =
      idle === 'sect_mining'
        ? '采矿中'
        : idle === 'spirit'
          ? '修炼中'
          : idle === 'body'
            ? '淬体中'
            : idle === 'crafting'
              ? '制造业修炼中'
              : '修炼中'
  } else if (craftRunning > 0) {
    mode = 'craft'
    modeLabel = `工坊进行中（${craftRunning}）`
  }

  const stopIdleMsg =
    productive
      ? idle === 'sect_mining'
        ? '采矿中不可操作，请先结束采矿'
        : '修炼中不可操作，请先停止修炼'
      : null
  const craftMsg =
    craftRunning > 0 ? '工坊仍有进行中任务，请先完成后再修炼' : null
  const statusMsg =
    status !== 'normal' ? `${modeLabel}不可操作` : null

  return {
    mode,
    mode_label: modeLabel,
    status,
    idle_direction: idle,
    craft_running: craftRunning,
    can_enter_idle: status === 'normal' && craftRunning === 0,
    can_start_craft: status === 'normal' && !productive,
    can_start_battle: status === 'normal' && !productive,
    can_breakthrough: status === 'normal' && !productive,
    can_quench: status === 'normal' && !productive,
    can_start_tribulation: status === 'normal' && !productive,
    blockers: {
      enter_idle: statusMsg || craftMsg,
      start_craft: statusMsg || stopIdleMsg,
      start_battle: statusMsg || stopIdleMsg,
      breakthrough: statusMsg || stopIdleMsg,
      quench: statusMsg || stopIdleMsg,
      start_tribulation: statusMsg || stopIdleMsg,
    },
  }
}

/**
 * 组合式：活动互斥门禁与提示文案。
 */
export function useActivityGate() {
  const characterStore = useCharacterStore()

  const activity = computed<ActivitySnapshot>(() => {
    return characterStore.character?.activity ?? deriveLocalActivity()
  })

  const modeLabel = computed(() => activity.value.mode_label)
  const isIdleBusy = computed(() => activity.value.mode === 'idle')
  const canEnterIdle = computed(() => activity.value.can_enter_idle)
  const canStartCraft = computed(() => activity.value.can_start_craft)
  const canStartBattle = computed(() => activity.value.can_start_battle)
  const canBreakthrough = computed(() => activity.value.can_breakthrough)
  const canQuench = computed(
    () => activity.value.can_quench ?? activity.value.can_breakthrough,
  )

  function blockReason(
    key: keyof ActivitySnapshot['blockers'],
  ): string | null {
    return activity.value.blockers?.[key] ?? null
  }

  return {
    activity,
    modeLabel,
    isIdleBusy,
    canEnterIdle,
    canStartCraft,
    canStartBattle,
    canBreakthrough,
    canQuench,
    blockReason,
  }
}
