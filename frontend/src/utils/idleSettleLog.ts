/**
 * 大厅修炼事件日志：满 10 周天发一条；主动停止时立刻冲刷剩余。
 */

export const IDLE_SETTLE_LOG_TICKS = 10

export interface IdleGainChunk {
  ticks: number
  cultivation: number
  body: number
  crafting: number
  stones: number
}

export function emptyGainChunk(): IdleGainChunk {
  return { ticks: 0, cultivation: 0, body: 0, crafting: 0, stones: 0 }
}

export function chunkFromIdleSync(data: {
  settled_ticks?: number
  gained_cultivation?: number
  gained_body?: number
  gained_crafting?: number
  spent_spirit_stones?: number
}): IdleGainChunk {
  return {
    ticks: Number(data.settled_ticks || 0),
    cultivation: Number(data.gained_cultivation || 0),
    body: Number(data.gained_body || 0),
    crafting: Number(data.gained_crafting || 0),
    stones: Number(data.spent_spirit_stones || 0),
  }
}

export function addGainChunk(buf: IdleGainChunk, add: IdleGainChunk): void {
  buf.ticks += add.ticks
  buf.cultivation += add.cultivation
  buf.body += add.body
  buf.crafting += add.crafting
  buf.stones += add.stones
}

export function formatIdleSettleLine(
  who: 'main' | 'avatar',
  chunk: IdleGainChunk,
  stopped: boolean,
): string | null {
  if (chunk.ticks <= 0) return null
  const whoZh = who === 'main' ? '本体' : '化身'
  const prefix = stopped ? `${whoZh}停止修炼，` : `${whoZh}，`
  const parts = [`修炼结算${chunk.ticks}周天`, `修为+${chunk.cultivation}`]
  if (chunk.body) parts.push(`淬体度+${chunk.body}`)
  if (chunk.crafting) parts.push(`制造业经验+${chunk.crafting}`)
  if (chunk.stones) parts.push(`灵石-${chunk.stones}`)
  return `${prefix}${parts.join('，')}`
}

/**
 * 从缓冲里切出满 10 周天的块；比例切增益避免一次 sync 塞入超过 10 时丢账。
 */
export function takeSettleChunks(
  buf: IdleGainChunk,
  size = IDLE_SETTLE_LOG_TICKS,
): IdleGainChunk[] {
  const out: IdleGainChunk[] = []
  while (buf.ticks >= size) {
    const ratio = size / buf.ticks
    const chunk: IdleGainChunk = {
      ticks: size,
      cultivation: Math.round(buf.cultivation * ratio),
      body: Math.round(buf.body * ratio),
      crafting: Math.round(buf.crafting * ratio),
      stones: Math.round(buf.stones * ratio),
    }
    buf.ticks -= size
    buf.cultivation -= chunk.cultivation
    buf.body -= chunk.body
    buf.crafting -= chunk.crafting
    buf.stones -= chunk.stones
    out.push(chunk)
  }
  return out
}

export function flushGainChunk(buf: IdleGainChunk): IdleGainChunk | null {
  if (buf.ticks <= 0) {
    Object.assign(buf, emptyGainChunk())
    return null
  }
  const copy = { ...buf }
  Object.assign(buf, emptyGainChunk())
  return copy
}
