/**
 * 战斗 Pinia store（M3）：本会话战报列表 + 体力 + 播放游标。
 *
 * 战报零保留（成型设计 §7.8）：服务器不落库、无历史接口；
 * 战报只存 sessionStorage，登出（clearOnLogout）或关闭浏览器后销毁。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchStaminaApi, startPveApi, startPvpApi } from '../api/battle'
import type {
  AutochessBattleResult,
  SessionReportEntry,
  StaminaState,
} from '../types/autochess'
import { useCharacterStore } from './character'

/** sessionStorage 键 */
const SESSION_REPORTS_KEY = 'xiuxian.battle.session_reports'
/** 会话内最多保留的战报数（事件量大，防内存膨胀） */
const MAX_SESSION_REPORTS = 20

/** 从 sessionStorage 恢复本会话战报（解析失败视为空）。 */
function loadSessionReports(): SessionReportEntry[] {
  try {
    const raw = sessionStorage.getItem(SESSION_REPORTS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as SessionReportEntry[]) : []
  } catch {
    return []
  }
}

export const useBattleStore = defineStore('battle', () => {
  const sessionReports = ref<SessionReportEntry[]>(loadSessionReports())
  /** 最近一场战报（开战响应原样） */
  const lastReport = ref<AutochessBattleResult | null>(null)
  /** 当前打开播放的 session_key */
  const activeReportKey = ref<string | null>(null)
  const stamina = ref<StaminaState | null>(null)
  const fighting = ref(false)

  /** 把内存列表同步到 sessionStorage。 */
  function persist(): void {
    try {
      sessionStorage.setItem(
        SESSION_REPORTS_KEY,
        JSON.stringify(sessionReports.value),
      )
    } catch {
      // sessionStorage 满：静默放弃（战报仍在内存中可播）
    }
  }

  /**
   * 把一场开战响应写入本会话战报列表。
   */
  function pushReport(payload: AutochessBattleResult): SessionReportEntry {
    const title =
      payload.mode === 'pve'
        ? `讨伐 ${payload.monster_name ?? payload.monster_id ?? '妖兽'}`
        : `攻打 ${payload.target?.dao_name ?? '无名氏'}`
    const entry: SessionReportEntry = {
      session_key: `r_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      created_at: new Date().toISOString(),
      mode: payload.mode,
      title,
      result: payload.result,
      payload,
    }
    const next = [entry, ...sessionReports.value]
    sessionReports.value =
      next.length > MAX_SESSION_REPORTS ? next.slice(0, MAX_SESSION_REPORTS) : next
    persist()
    return entry
  }

  /**
   * 开战成功后的统一入账：角色 / 体力 / 战报。
   */
  function applyBattleResult(payload: AutochessBattleResult): SessionReportEntry {
    useCharacterStore().applyCharacter(payload.character)
    stamina.value = payload.stamina
    lastReport.value = payload
    const entry = pushReport(payload)
    activeReportKey.value = entry.session_key
    return entry
  }

  /**
   * 发起 PVE。
   *
   * @returns 错误消息；成功为 null
   */
  async function startPve(
    monsterId: string,
    presetSlot: number | null = null,
    useDao = false,
  ): Promise<string | null> {
    if (fighting.value) return '战斗进行中'
    fighting.value = true
    try {
      const envelope = await startPveApi(monsterId, presetSlot, useDao)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `开战失败（code=${envelope.code}）`
      }
      applyBattleResult(envelope.data)
      return null
    } finally {
      fighting.value = false
    }
  }

  /**
   * 发起 PVP（攻打快照）。
   *
   * @returns 错误消息；成功为 null
   */
  async function startPvp(
    targetCharacterId: number,
    presetSlot: number | null = null,
    useDao = false,
  ): Promise<string | null> {
    if (fighting.value) return '战斗进行中'
    fighting.value = true
    try {
      const envelope = await startPvpApi(targetCharacterId, presetSlot, useDao)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `开战失败（code=${envelope.code}）`
      }
      applyBattleResult(envelope.data)
      return null
    } finally {
      fighting.value = false
    }
  }

  /** 刷新体力读数。 */
  async function refreshStamina(): Promise<void> {
    const envelope = await fetchStaminaApi()
    if (envelope.code === 0 && envelope.data) {
      stamina.value = envelope.data
    }
  }

  /** 登出时清空本会话战报（隐私 + 设计约定）。 */
  function clearOnLogout(): void {
    sessionReports.value = []
    lastReport.value = null
    activeReportKey.value = null
    stamina.value = null
    try {
      sessionStorage.removeItem(SESSION_REPORTS_KEY)
    } catch {
      // 忽略
    }
  }

  return {
    sessionReports,
    lastReport,
    activeReportKey,
    stamina,
    fighting,
    startPve,
    startPvp,
    refreshStamina,
    applyBattleResult,
    clearOnLogout,
  }
})
