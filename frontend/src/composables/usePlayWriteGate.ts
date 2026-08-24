/**
 * Lifecycle write gate for M8 polish: tribulation / ferry / reincarnating → UI read-only.
 * Server still enforces 40211 / 40076; this avoids click-then-error.
 */
import { computed } from 'vue'
import { useCharacterStore } from '../stores/character'

/** Statuses that block research / equip / scribe writes. */
const WRITE_BLOCK_STATUSES = new Set(['tribulation', 'awaiting_ferry', 'reincarnating'])

export function usePlayWriteGate() {
  const characterStore = useCharacterStore()

  const status = computed(() => characterStore.character?.status ?? 'normal')

  const writeBlocked = computed(() => WRITE_BLOCK_STATUSES.has(status.value))

  const writeBlockReason = computed(() => {
    if (status.value === 'tribulation') return '渡劫中不可在研究室定稿、画符或改穿戴（可只读浏览）'
    if (status.value === 'awaiting_ferry') return '待引渡期间不可在研究室定稿、画符或改穿戴（可只读浏览）'
    if (status.value === 'reincarnating') return '轮回新生中不可在研究室定稿、画符或改穿戴'
    return ''
  })

  return {
    status,
    writeBlocked,
    writeBlockReason,
  }
}
