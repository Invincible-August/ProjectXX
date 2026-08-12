/**
 * GM API：仅开发联调（M1～M6）；生产构建 UI 不展示入口。
 */
import { http } from './http'
import { envelopeFromAxiosError } from './envelope'
import type { ApiResponse } from '../types/api'
import type { CharacterPublic } from '../types/character'

/** GM 写入字段（皆可选） */
export interface GmSetCharacterPayload {
  major_realm?: string
  realm_stage?: number
  cultivation_points?: number
  realm_progress?: number
  body_tempering_points?: number
  crafting_exp?: number
  spirit_stones?: number
  idle_direction?: string
  status?: string
  breakthrough_grade?: string
  membership_tier?: string
  clear_offline_pending?: boolean
  // --- M3 战斗成型调试字段 ---
  /** 直接设置体力值 */
  set_stamina?: number
  /** 设置试炼木傀持有数 */
  trial_puppet_count?: number
  /** 清除快照手动更新冷却 */
  reset_snapshot_cooldown?: boolean
  /** 立即用当前防守预设重建快照 */
  force_refresh_snapshot?: boolean
  // --- M4 双线程调试字段 ---
  /** 一键提升至金丹（联调用） */
  force_jindan?: boolean
  /** 发放工坊材料样本 */
  grant_craft_materials?: boolean
  /** 发放测试灵宠 */
  grant_test_pet?: boolean
  /** 清空工坊队列 */
  clear_craft_jobs?: boolean
  /** 神识容量 GM 加成 */
  divine_sense_capacity_bonus?: number
  /** 清除神识反噬标记 */
  clear_divine_sense_backlash?: boolean
  /** 阵法钻研等级 */
  array_craft_level?: number
  // --- M5 环境与轮回调试 ---
  /** 强制当前时辰 */
  force_shichen?: string
  /** 强制天气 */
  force_weather?: string
  /** 灵根环境标签（参与 tag_modifiers；空数组清空） */
  spirit_root_tags?: string[]
  /** 强制渡劫结局：won / failed / fallen */
  force_tribulation_outcome?: string
  /** 发放验收体质（主/副词条）并自动镶嵌 */
  grant_acceptance_constitution?: boolean
  /** 一键开启渡劫会话 */
  start_tribulation?: boolean
  /** 置为待引渡 */
  set_awaiting_ferry?: boolean
  /** 立即触发待引渡超时轮回 */
  force_ferry_timeout?: boolean
  /** 标记剧情已历节点 */
  mark_story_node?: string
  /** 一键元婴大圆满 */
  force_yuanying_peak?: boolean
  // --- M6 大道 / 道主 ---
  /** 一键真仙初期（可开道） */
  force_true_immortal?: boolean
  /** 灌入道池 id 列表 */
  grant_dao_pool?: string[]
  /** 任命道主；空字符串清空自己的道主身份 */
  set_dao_lord?: string
  /** 强制挑战开窗（进程标志） */
  open_dao_challenge_window?: boolean
  /** M6-D06：立刻开赛（进程标志） */
  open_dao_contest_now?: boolean
  /** 清空挑战冷却 */
  clear_dao_challenge_cooldown?: boolean
  /** 经 WS 推一条 world.env */
  push_world_env?: boolean
  /** 直接设道值 */
  set_dao_qi?: number
  /** 直接设道等级 */
  set_dao_level?: number
  /** 跳过 roll 锁定本命道 */
  lock_fate_dao?: string
  /** 一键 M6 联调套装 */
  m6_quick_kit?: boolean
}

/**
 * POST /gm/character/set
 *
 * @param payload - 至少一项
 */
export async function gmSetCharacterApi(
  payload: GmSetCharacterPayload,
): Promise<ApiResponse<{ character: CharacterPublic }>> {
  try {
    const response = await http.post<ApiResponse<{ character: CharacterPublic }>>(
      '/gm/character/set',
      payload,
    )
    return response.data
  } catch (error: unknown) {
    return envelopeFromAxiosError<{ character: CharacterPublic }>(error)
  }
}

/** M5：强制时辰（经 character/set） */
export async function gmForceShichenApi(
  shichen: string,
): Promise<ApiResponse<{ character: CharacterPublic }>> {
  return gmSetCharacterApi({ force_shichen: shichen })
}

/** M5：强制天气 */
export async function gmForceWeatherApi(
  weather: string,
): Promise<ApiResponse<{ character: CharacterPublic }>> {
  return gmSetCharacterApi({ force_weather: weather })
}

/** M5：写入灵根环境标签 */
export async function gmSetSpiritRootTagsApi(
  tags: string[],
): Promise<ApiResponse<{ character: CharacterPublic }>> {
  return gmSetCharacterApi({ spirit_root_tags: tags })
}

/** M5：一键开渡劫 */
export async function gmStartTribulationApi(): Promise<
  ApiResponse<{ character: CharacterPublic }>
> {
  return gmSetCharacterApi({ start_tribulation: true })
}

/** M5：强制渡劫结局（验收） */
export async function gmForceTribulationOutcomeApi(
  outcome: 'won' | 'failed' | 'fallen',
): Promise<ApiResponse<{ character: CharacterPublic }>> {
  return gmSetCharacterApi({ force_tribulation_outcome: outcome })
}

/** M5：发放验收体质并自动镶嵌 */
export async function gmGrantAcceptanceConstitutionApi(): Promise<
  ApiResponse<{ character: CharacterPublic }>
> {
  return gmSetCharacterApi({ grant_acceptance_constitution: true })
}

/** M5：置待引渡 */
export async function gmSetAwaitingFerryApi(): Promise<
  ApiResponse<{ character: CharacterPublic }>
> {
  return gmSetCharacterApi({ set_awaiting_ferry: true })
}

/** M5：立即超时轮回 */
export async function gmForceFerryTimeoutApi(): Promise<
  ApiResponse<{ character: CharacterPublic }>
> {
  return gmSetCharacterApi({ force_ferry_timeout: true })
}

/** M5：标记 story 节点 */
export async function gmMarkStoryNodeApi(
  nodeId: string,
): Promise<ApiResponse<{ character: CharacterPublic }>> {
  return gmSetCharacterApi({ mark_story_node: nodeId })
}

/** M6：一键真仙 */
export async function gmForceTrueImmortalApi(): Promise<
  ApiResponse<{ character: CharacterPublic }>
> {
  return gmSetCharacterApi({ force_true_immortal: true })
}

/** M6：一键联调套装 */
export async function gmM6QuickKitApi(): Promise<
  ApiResponse<{ character: CharacterPublic }>
> {
  return gmSetCharacterApi({ m6_quick_kit: true })
}

/** M6：锁本命道 */
export async function gmLockFateDaoApi(
  daoId: string,
): Promise<ApiResponse<{ character: CharacterPublic }>> {
  return gmSetCharacterApi({ lock_fate_dao: daoId })
}

/** M6：设道资源 */
export async function gmSetDaoResourcesApi(opts: {
  qi?: number
  level?: number
}): Promise<ApiResponse<{ character: CharacterPublic }>> {
  return gmSetCharacterApi({
    set_dao_qi: opts.qi,
    set_dao_level: opts.level,
  })
}

/** M6：任命/清空道主 */
export async function gmSetDaoLordApi(
  daoId: string,
): Promise<ApiResponse<{ character: CharacterPublic }>> {
  return gmSetCharacterApi({ set_dao_lord: daoId })
}

/** M6：强制开窗 */
export async function gmOpenDaoChallengeWindowApi(): Promise<
  ApiResponse<{ character: CharacterPublic }>
> {
  return gmSetCharacterApi({ open_dao_challenge_window: true })
}

/** M6-D06 P1：立刻开赛 */
export async function gmOpenDaoContestNowApi(): Promise<
  ApiResponse<{ character: CharacterPublic }>
> {
  return gmSetCharacterApi({ open_dao_contest_now: true })
}

/** M6：推 world.env */
export async function gmPushWorldEnvApi(): Promise<
  ApiResponse<{ character: CharacterPublic }>
> {
  return gmSetCharacterApi({ push_world_env: true })
}
