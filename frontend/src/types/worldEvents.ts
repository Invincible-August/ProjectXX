/**
 * M6 世界事件骨架类型（Boss / 秘境入口占位；成型玩法 → M11）。
 */

/** 事件种类 */
export type WorldEventKind =
  | 'world_boss'
  | 'secret_realm'
  | 'world_broadcast'
  | string

/** 单个进行中 / 即将开放的事件摘要 */
export interface WorldEventPublic {
  id: string | number
  kind: WorldEventKind
  /** 中文标题 */
  label: string
  /** 是否标注为骨架 */
  skeleton?: boolean
  placeholder?: boolean
  /** 是否开放报名/进入 */
  open: boolean
  /** 房间 id（WS join 用） */
  room_id?: string | null
  /** WS 在场人数 */
  presence_count?: number
  /** 仅报名人数（未 join 不计入在场） */
  registered_count?: number
  /** 开放 / 关闭时刻 */
  opens_at?: string | null
  closes_at?: string | null
  /** 说明文案 */
  description?: string
  summary?: string
  /** 是否已报名 */
  registered?: boolean
}

/** GET /world-events/current */
export interface WorldEventsCurrentPayload {
  events: WorldEventPublic[]
  /** 页眉说明 */
  note?: string
  /** 后端 hint 别名 */
  hint?: string
  enabled?: boolean
}

/** POST register 结果 */
export interface WorldEventRegisterResult {
  event?: WorldEventPublic
  message?: string
  room_id?: string
}
