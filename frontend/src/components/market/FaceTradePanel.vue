<script setup lang="ts">
/**
 * 交易面板（社交 · 交易）：邮件同款写信台布局。
 * 右侧快捷选人（道友/师徒/宗门/道侣）+ 道号；4×4 道具格点空开背包、点满移除。
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useInventoryStore } from '../../stores/inventory'
import { useTradeStore } from '../../stores/trade'
import type { InventoryItem } from '../../types/inventory'
import type { FaceInviteTarget, TradeItemLine } from '../../types/trade'
import { parseNonNegInt } from '../../utils/intMoney'

const props = defineProps<{
  /** 路由 query.peer：角色 id 或道号预填 */
  peer?: string | null
  /** 已有会话 id（可选深链） */
  sessionId?: number | null
}>()

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
  'session-change': [sessionId: number | null]
}>()

type OfferSlot = {
  item_id: string
  name: string
  quantity: number
  max_stack: number
  bag_have: number
} | null

type PickKind = 'friend' | 'mentor' | 'sect' | 'companion'

const route = useRoute()
const tradeStore = useTradeStore()
const inventoryStore = useInventoryStore()
const busy = ref(false)
const loadError = ref('')
let autoSaveTimer: ReturnType<typeof setTimeout> | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

const peerName = ref('')
const selectedPeerId = ref<number | null>(null)
const offerStones = ref(0)
const offerSlots = ref<OfferSlot[]>([])
const vesselOfferEnabled = ref(false)
const vesselHours = ref(24)

const pickDialogVisible = ref(false)
const pickKind = ref<PickKind>('friend')
const bagVisible = ref(false)
const qtyPopover = ref<{
  visible: boolean
  left: number
  top: number
  item: InventoryItem | null
  quantity: number
  maxQty: number
}>({
  visible: false,
  left: 0,
  top: 0,
  item: null,
  quantity: 1,
  maxQty: 1,
})

const session = computed(() => tradeStore.faceSession)
const vesselCtx = computed(() => session.value?.vessel_context ?? null)
const maxLines = computed(
  () => Number(tradeStore.inviteOptions?.face_max_item_lines ?? 16),
)

const canOfferVessel = computed(() => {
  const ctx = vesselCtx.value
  if (!ctx) return false
  if (theirOffer.value?.vessel_offer) return false
  return Boolean(ctx.can_offer_become || ctx.can_offer_extend)
})

const vesselOfferHint = computed(() => {
  const ctx = vesselCtx.value
  if (!ctx) return ''
  if (ctx.relation === 'i_am_master') return '你已是对方主人，不可再成为其炉鼎'
  if (ctx.are_companions) return '互为道侣不可成为对方炉鼎（可为他人炉鼎）'
  if (theirOffer.value?.vessel_offer) return '对方已要约炉鼎，本侧不可再要约'
  if (ctx.can_offer_extend) return '可延长现有炉鼎时限（现实小时）'
  if (ctx.can_offer_become) return '可要约成为对方炉鼎（现实小时）'
  return '当前不可要约炉鼎'
})

const myOffer = computed(() => {
  const s = session.value
  if (!s) return null
  return s.you_are === 'initiator' ? s.initiator_offer : s.peer_offer
})

const theirOffer = computed(() => {
  const s = session.value
  if (!s) return null
  return s.you_are === 'initiator' ? s.peer_offer : s.initiator_offer
})

const iAmLocked = computed(() => {
  const s = session.value
  if (!s) return false
  return s.you_are === 'initiator' ? s.initiator_locked : s.peer_locked
})

const theyLocked = computed(() => {
  const s = session.value
  if (!s) return false
  return s.you_are === 'initiator' ? s.peer_locked : s.initiator_locked
})

const iAmConfirmed = computed(() => {
  const s = session.value
  if (!s) return false
  return s.you_are === 'initiator' ? s.initiator_confirmed : s.peer_confirmed
})

const theyConfirmed = computed(() => {
  const s = session.value
  if (!s) return false
  return s.you_are === 'initiator' ? s.peer_confirmed : s.initiator_confirmed
})

const canAct = computed(() => {
  const st = session.value?.status
  return Boolean(st && !['committed', 'cancelled', 'expired'].includes(st))
})

const isPendingInvite = computed(() => session.value?.status === 'pending_invite')
const isPeerViewer = computed(() => session.value?.you_are === 'peer')
/** 已接受后的正式交易台（未发起 / 待接受时不展示） */
const showOfferWorkspace = computed(() => {
  const st = session.value?.status
  return st === 'browsing' || st === 'locking' || st === 'confirming'
})
const showInviteCompose = computed(() => !showOfferWorkspace.value)
const pendingInvites = computed(() => tradeStore.pendingInvites)
const counterpartyName = computed(() => {
  const s = session.value
  if (!s) return ''
  return s.you_are === 'initiator' ? s.peer_name : s.initiator_name
})
const canDraft = computed(() => {
  const st = session.value?.status
  if (!st || !canAct.value) return false
  if (iAmLocked.value) return false
  return st === 'browsing' || (st === 'locking' && !iAmLocked.value)
})
const canLock = computed(
  () =>
    canAct.value &&
    (session.value?.status === 'browsing' || session.value?.status === 'locking') &&
    !iAmLocked.value,
)
const canConfirm = computed(() => {
  const st = session.value?.status
  return (
    canAct.value &&
    Boolean(session.value?.initiator_locked && session.value?.peer_locked) &&
    (st === 'locking' || st === 'confirming') &&
    !iAmConfirmed.value
  )
})

const tradableBag = computed(() =>
  inventoryStore.normalItems.filter((x) => x.tradable !== false && !x.bound),
)

const filledSlotCount = computed(
  () => offerSlots.value.filter((s) => s != null).length,
)

const pickDialogTitle = computed(() => {
  if (pickKind.value === 'mentor') return '选择师徒'
  if (pickKind.value === 'sect') return '选择同门'
  if (pickKind.value === 'companion') return '选择道侣'
  return '选择道友'
})

const pickList = computed((): FaceInviteTarget[] => {
  const opts = tradeStore.inviteOptions
  if (!opts) return []
  if (pickKind.value === 'mentor') return opts.mentors
  if (pickKind.value === 'sect') return opts.sect_members
  if (pickKind.value === 'companion') return opts.companions
  return opts.friends
})

function ensureSlotGrid(): void {
  const n = maxLines.value
  offerSlots.value = Array.from({ length: n }, (_, i) => offerSlots.value[i] ?? null)
}

function applyPeerPrefill(raw: string | null | undefined): void {
  const v = (raw || '').trim()
  if (!v) return
  if (/^\d+$/.test(v)) {
    selectedPeerId.value = Number(v)
    peerName.value = ''
  } else {
    selectedPeerId.value = null
    peerName.value = v
  }
}

function itemMeta(itemId: string): { name: string; max_stack: number; bag_have: number } {
  const bag = tradableBag.value.find((x) => x.item_id === itemId)
  return {
    name: bag?.name || itemId,
    max_stack: Number(bag?.max_stack || 99),
    bag_have: Number(bag?.quantity || 0),
  }
}

function syncDraftFromSession(): void {
  const offer = myOffer.value
  ensureSlotGrid()
  if (!offer) {
    offerSlots.value = Array.from({ length: maxLines.value }, () => null)
    offerStones.value = 0
    vesselOfferEnabled.value = false
    vesselHours.value = vesselCtx.value?.vessel_min_hours || 24
    return
  }
  const next: OfferSlot[] = Array.from({ length: maxLines.value }, () => null)
  ;(offer.items ?? []).slice(0, maxLines.value).forEach((line, idx) => {
    const meta = itemMeta(line.item_id)
    next[idx] = {
      item_id: line.item_id,
      name: meta.name,
      quantity: Number(line.quantity) || 1,
      max_stack: meta.max_stack,
      bag_have: meta.bag_have,
    }
  })
  offerSlots.value = next
  offerStones.value = parseNonNegInt(offer.spirit_stones) ?? 0
  const vo = offer.vessel_offer
  vesselOfferEnabled.value = Boolean(vo && (parseNonNegInt(vo.hours) ?? 0) > 0)
  vesselHours.value =
    parseNonNegInt(vo?.hours) ?? vesselCtx.value?.vessel_min_hours ?? 24
}

function draftLines(): TradeItemLine[] {
  return offerSlots.value
    .filter((s): s is NonNullable<OfferSlot> => s != null)
    .map((s) => ({ item_id: s.item_id, quantity: Math.max(1, Number(s.quantity) || 1) }))
}

function clearSlot(idx: number): void {
  if (!canDraft.value) return
  offerSlots.value[idx] = null
  offerSlots.value = [...offerSlots.value]
}

function openBag(): void {
  if (!canDraft.value) {
    ElMessage.warning('当前不可改报价')
    return
  }
  qtyPopover.value.visible = false
  bagVisible.value = true
}

function firstEmptySlot(): number {
  return offerSlots.value.findIndex((s) => s == null)
}

function bagItemDisabled(item: InventoryItem): boolean {
  if (!canDraft.value) return true
  if (offerSlots.value.some((s) => s?.item_id === item.item_id)) return false
  return filledSlotCount.value >= maxLines.value
}

function onBagCellClick(item: InventoryItem, ev: MouseEvent): void {
  if (bagItemDisabled(item)) return
  const existingIdx = offerSlots.value.findIndex((s) => s?.item_id === item.item_id)
  const maxQty = Math.max(1, Number(item.quantity) || 1)
  qtyPopover.value = {
    visible: true,
    left: Math.min(ev.clientX, window.innerWidth - 180),
    top: Math.min(ev.clientY, window.innerHeight - 120),
    item,
    quantity: existingIdx >= 0 ? Number(offerSlots.value[existingIdx]?.quantity || 1) : 1,
    maxQty,
  }
}

function confirmQty(): void {
  const pop = qtyPopover.value
  const item = pop.item
  if (!item) return
  const qty = Math.min(Math.max(1, Number(pop.quantity) || 1), pop.maxQty)
  const existingIdx = offerSlots.value.findIndex((s) => s?.item_id === item.item_id)
  if (existingIdx >= 0) {
    const cur = offerSlots.value[existingIdx]
    if (cur) {
      offerSlots.value[existingIdx] = { ...cur, quantity: qty }
      offerSlots.value = [...offerSlots.value]
    }
  } else {
    const slotIdx = firstEmptySlot()
    if (slotIdx < 0) {
      ElMessage.warning('道具栏已满（最多 16 种）')
      return
    }
    offerSlots.value[slotIdx] = {
      item_id: item.item_id,
      name: item.name || item.item_id,
      quantity: qty,
      max_stack: Number(item.max_stack || 99),
      bag_have: Number(item.quantity || 0),
    }
    offerSlots.value = [...offerSlots.value]
  }
  qtyPopover.value.visible = false
  bagVisible.value = false
}

function openPickDialog(kind: PickKind): void {
  pickKind.value = kind
  pickDialogVisible.value = true
}

function pickTarget(t: FaceInviteTarget): void {
  selectedPeerId.value = Number(t.character_id)
  peerName.value = t.name
  pickDialogVisible.value = false
}

function startPolling(): void {
  stopPolling()
  pollTimer = setInterval(async () => {
    const id = session.value?.id
    if (!id || !canAct.value || busy.value) return
    await tradeStore.loadFace(id)
  }, 3000)
}

function stopPolling(): void {
  if (pollTimer != null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onMounted(async () => {
  applyPeerPrefill(props.peer)
  const prefill = route.query.to
  if (typeof prefill === 'string' && prefill.trim()) {
    applyPeerPrefill(prefill.trim())
  }
  loadError.value = ''
  const sid = props.sessionId && props.sessionId > 0 ? props.sessionId : null
  const [errOpt, errInv] = await Promise.all([
    tradeStore.loadInviteOptions(),
    sid
      ? tradeStore.refreshPendingWithRetry(sid)
      : tradeStore.refreshPending(),
    inventoryStore.load(),
  ])
  ensureSlotGrid()
  if (errOpt || errInv) {
    loadError.value = errOpt || errInv || ''
    emit('log', loadError.value, 'warning')
  }
  if (sid) {
    const err = await tradeStore.loadFace(sid)
    if (err) {
      // 提交竞态时短重试一次
      await new Promise((r) => setTimeout(r, 200))
      const err2 = await tradeStore.loadFace(sid)
      if (err2) {
        ElMessage.error(err2)
        emit('log', err2, 'warning')
      }
    }
    if (tradeStore.faceSession) {
      emit('session-change', tradeStore.faceSession.id)
      syncDraftFromSession()
      if (canAct.value) startPolling()
    }
  }
})

onUnmounted(() => {
  stopPolling()
  if (autoSaveTimer != null) clearTimeout(autoSaveTimer)
})

watch(
  () => props.peer,
  (v) => applyPeerPrefill(v),
)

watch(
  () => session.value?.id,
  (id) => {
    emit('session-change', id ?? null)
    if (id && canAct.value) startPolling()
    else stopPolling()
  },
)

watch(
  () => session.value?.version,
  () => {
    if (!iAmLocked.value) syncDraftFromSession()
  },
)

watch(maxLines, () => ensureSlotGrid())

watch(
  [offerSlots, offerStones, vesselOfferEnabled, vesselHours],
  () => {
    if (showOfferWorkspace.value && canDraft.value) scheduleAutoSave()
  },
  { deep: true },
)

watch(
  () => props.sessionId,
  async (sid) => {
    if (!sid || sid <= 0) return
    await tradeStore.refreshPendingWithRetry(sid)
    if (session.value?.id === sid && session.value.status === 'pending_invite') {
      return
    }
    if (session.value?.id === sid && showOfferWorkspace.value) {
      syncDraftFromSession()
      startPolling()
      return
    }
    let err = await tradeStore.loadFace(sid)
    if (err) {
      await new Promise((r) => setTimeout(r, 200))
      err = await tradeStore.loadFace(sid)
    }
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    syncDraftFromSession()
    if (canAct.value) startPolling()
  },
)

async function onInvite(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    let err: string | null
    if (selectedPeerId.value && selectedPeerId.value > 0) {
      err = await tradeStore.inviteFace({
        peer_character_id: selectedPeerId.value,
        peer_name: peerName.value.trim() || undefined,
      })
    } else {
      const name = peerName.value.trim()
      if (!name) {
        ElMessage.warning('请输入对方道号，或右侧快捷选择')
        return
      }
      err = await tradeStore.inviteFace({ peer_name: name })
    }
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    syncDraftFromSession()
    startPolling()
    ElMessage.success(tradeStore.lastMessage || '已发起交易')
    emit('log', tradeStore.lastMessage || '交易已发起', 'success')
  } finally {
    busy.value = false
  }
}

async function onRefresh(): Promise<void> {
  const id = session.value?.id
  if (!id) return
  busy.value = true
  try {
    const err = await tradeStore.loadFace(id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
    }
  } finally {
    busy.value = false
  }
}

async function autoSaveOffer(silent = true): Promise<string | null> {
  if (!canDraft.value || busy.value) return null
  if (!draftDirty()) return null
  const stones = parseNonNegInt(offerStones.value)
  if (stones === null) {
    const msg = '灵石须为 ≥ 0 的整数'
    if (!silent) {
      ElMessage.error(msg)
      emit('log', msg, 'warning')
    }
    return msg
  }
  let vessel: { hours: number } | null = null
  if (vesselOfferEnabled.value) {
    const hours = parseNonNegInt(vesselHours.value)
    if (hours === null) {
      const msg = '炉鼎时限须为 ≥ 0 的整数'
      if (!silent) {
        ElMessage.error(msg)
        emit('log', msg, 'warning')
      }
      return msg
    }
    if (hours <= 0) {
      const msg = '炉鼎时限须 ≥ 1'
      if (!silent) {
        ElMessage.error(msg)
        emit('log', msg, 'warning')
      }
      return msg
    }
    vessel = { hours }
  }
  busy.value = true
  try {
    const err = await tradeStore.setFaceOffer(draftLines(), stones, vessel)
    if (err) {
      if (!silent) {
        ElMessage.error(err)
        emit('log', err, 'warning')
      }
      return err
    }
    return null
  } finally {
    busy.value = false
  }
}

function scheduleAutoSave(): void {
  if (!canDraft.value) return
  if (autoSaveTimer != null) clearTimeout(autoSaveTimer)
  autoSaveTimer = setTimeout(() => {
    void autoSaveOffer(true)
  }, 450)
}

async function openPendingInvite(sessionId: number): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await tradeStore.loadFace(sessionId)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    emit('session-change', sessionId)
  } finally {
    busy.value = false
  }
}

async function acceptPending(sessionId: number): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    let err = await tradeStore.loadFace(sessionId)
    if (!err) err = await tradeStore.acceptFace()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    await Promise.all([inventoryStore.load(), tradeStore.refreshPending()])
    syncDraftFromSession()
    startPolling()
    ElMessage.success(tradeStore.lastMessage || '已接受')
    emit('log', tradeStore.lastMessage || '交易已接受', 'success')
  } finally {
    busy.value = false
  }
}

async function rejectPending(sessionId: number): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    let err = await tradeStore.loadFace(sessionId)
    if (!err) err = await tradeStore.rejectFace()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    stopPolling()
    await tradeStore.refreshPending()
    ElMessage.success(tradeStore.lastMessage || '已拒绝')
    emit('log', tradeStore.lastMessage || '交易已拒绝', 'info')
  } finally {
    busy.value = false
  }
}

function backToInvite(): void {
  stopPolling()
  tradeStore.clearFaceSession()
  emit('session-change', null)
}

async function onAccept(): Promise<void> {
  if (busy.value || !isPendingInvite.value || !isPeerViewer.value) return
  busy.value = true
  try {
    const err = await tradeStore.acceptFace()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    await Promise.all([inventoryStore.load(), tradeStore.refreshPending()])
    ElMessage.success(tradeStore.lastMessage || '已接受')
    emit('log', tradeStore.lastMessage || '交易已接受', 'success')
  } finally {
    busy.value = false
  }
}

async function onReject(): Promise<void> {
  if (busy.value || !isPendingInvite.value || !isPeerViewer.value) return
  busy.value = true
  try {
    const err = await tradeStore.rejectFace()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    stopPolling()
    await tradeStore.refreshPending()
    ElMessage.success(tradeStore.lastMessage || '已拒绝')
    emit('log', tradeStore.lastMessage || '交易已拒绝', 'info')
  } finally {
    busy.value = false
  }
}

function draftDirty(): boolean {
  const server = myOffer.value
  const lines = draftLines()
  const stones = parseNonNegInt(offerStones.value) ?? 0
  const serverLines = (server?.items ?? []).map((x) => ({
    item_id: x.item_id,
    quantity: Number(x.quantity) || 0,
  }))
  const localLines = lines.map((x) => ({
    item_id: x.item_id,
    quantity: Number(x.quantity) || 0,
  }))
  if (JSON.stringify(serverLines) !== JSON.stringify(localLines)) return true
  if (Number(server?.spirit_stones || 0) !== stones) return true
  const serverVessel = server?.vessel_offer?.hours ?? null
  const localVessel = vesselOfferEnabled.value
    ? parseNonNegInt(vesselHours.value)
    : null
  if (vesselOfferEnabled.value && localVessel === null) return true
  return serverVessel !== (vesselOfferEnabled.value ? localVessel : null)
}

async function onLock(): Promise<void> {
  if (busy.value || !canLock.value) return
  if (canDraft.value && draftDirty()) {
    const syncErr = await autoSaveOffer(false)
    if (syncErr) return
  }
  busy.value = true
  try {
    const err = await tradeStore.lockFace()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    await inventoryStore.load()
    ElMessage.success(tradeStore.lastMessage || '已锁定')
    emit('log', tradeStore.lastMessage || '交易已锁定', 'success')
  } finally {
    busy.value = false
  }
}

async function onConfirm(): Promise<void> {
  if (busy.value || !canConfirm.value) return
  busy.value = true
  try {
    const err = await tradeStore.confirmFace()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    await inventoryStore.load()
    ElMessage.success(tradeStore.lastMessage || '已确认')
    emit('log', tradeStore.lastMessage || '交易确认', 'success')
  } finally {
    busy.value = false
  }
}

async function onCancel(): Promise<void> {
  if (busy.value || !canAct.value) return
  busy.value = true
  try {
    const err = await tradeStore.cancelFace()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    stopPolling()
    await inventoryStore.load()
    ElMessage.success(tradeStore.lastMessage || '已取消')
    emit('log', tradeStore.lastMessage || '交易已取消', 'info')
  } finally {
    busy.value = false
  }
}

function formatOffer(
  offer: {
    items: { item_id: string; quantity: number }[]
    spirit_stones: number
    vessel_offer?: { hours: number } | null
  } | null,
): string {
  if (!offer) return '—'
  const parts = (offer.items ?? []).map((l) => {
    const meta = itemMeta(l.item_id)
    return `${meta.name}×${l.quantity}`
  })
  if (offer.spirit_stones) parts.push(`${offer.spirit_stones} 灵石`)
  if (offer.vessel_offer?.hours) {
    parts.push(`愿为炉鼎 ${offer.vessel_offer.hours} 小时`)
  }
  return parts.length ? parts.join('、') : '（空）'
}

async function focusPeerInput(): Promise<void> {
  await nextTick()
}
</script>

<template>
  <el-card shadow="never" class="face-panel">
    <template #header>
      <div class="hdr">
        <el-text tag="b">交易</el-text>
        <el-text size="small" type="info">须有社交关系且双方在线</el-text>
      </div>
    </template>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      :closable="false"
      show-icon
      class="hint"
    />

    <!-- 待接受交易列表 -->
    <section v-if="pendingInvites.length" class="pending-box">
      <div class="compose-title-row">
        <el-text tag="b" size="small">待接受交易</el-text>
        <el-text size="small" type="info">{{ pendingInvites.length }} 条</el-text>
      </div>
      <div
        v-for="p in pendingInvites"
        :key="p.session_id"
        class="pending-row"
      >
        <el-text size="small">
          <el-text tag="b" size="small">{{ p.from_name }}</el-text>
          发起交易
        </el-text>
        <div class="pending-actions">
          <el-button size="small" :loading="busy" @click="openPendingInvite(p.session_id)">
            查看
          </el-button>
          <el-button
            type="primary"
            size="small"
            :loading="busy"
            @click="acceptPending(p.session_id)"
          >
            接受
          </el-button>
          <el-button
            size="small"
            type="danger"
            plain
            :loading="busy"
            @click="rejectPending(p.session_id)"
          >
            拒绝
          </el-button>
        </div>
      </div>
    </section>

    <!-- 发起台：无进行中交易时显示 -->
    <section v-if="showInviteCompose" class="compose-stage">
      <div class="compose-main">
        <div class="compose-title-row">
          <el-text tag="b">发起交易</el-text>
          <el-text size="small" type="info">须有社交关系且双方在线</el-text>
        </div>

        <template v-if="isPendingInvite && session">
          <el-alert
            v-if="isPeerViewer"
            :title="`「${counterpartyName}」向你发起交易，请接受或拒绝`"
            type="warning"
            :closable="false"
            show-icon
            class="hint"
          />
          <el-alert
            v-else
            :title="`已向「${counterpartyName}」发起，等待对方接受…`"
            type="info"
            :closable="false"
            show-icon
            class="hint"
          />
          <div class="form-row">
            <template v-if="isPeerViewer">
              <el-button type="primary" size="small" :loading="busy" @click="onAccept">
                接受
              </el-button>
              <el-button size="small" type="danger" plain :loading="busy" @click="onReject">
                拒绝
              </el-button>
            </template>
            <el-button size="small" type="danger" plain :loading="busy" @click="onCancel">
              取消
            </el-button>
            <el-button size="small" :loading="busy" @click="onRefresh">刷新</el-button>
          </div>
        </template>

        <template v-else>
          <label class="field-label">对方道号</label>
          <el-input
            v-model="peerName"
            placeholder="道号（或右侧快捷选择）"
            size="small"
            clearable
            @clear="selectedPeerId = null"
            @keyup.enter="onInvite"
            @focus="focusPeerInput"
          />
          <el-button
            type="primary"
            class="invite-btn"
            :loading="busy"
            @click="onInvite"
          >
            发起交易
          </el-button>
          <el-alert
            v-if="session && !canAct"
            :title="`上一笔已结束：${session.status_label_zh}`"
            type="info"
            :closable="false"
            show-icon
            class="hint"
          />
          <el-button
            v-if="session && !canAct"
            size="small"
            class="invite-btn"
            @click="backToInvite"
          >
            清除并继续
          </el-button>
        </template>
      </div>
      <aside class="compose-side">
        <el-button size="small" @click="openPickDialog('friend')">道友</el-button>
        <el-button size="small" @click="openPickDialog('mentor')">师徒</el-button>
        <el-button size="small" @click="openPickDialog('sect')">宗门</el-button>
        <el-button size="small" @click="openPickDialog('companion')">道侣</el-button>
      </aside>
    </section>

    <!-- 正式交易台：仅双方接受后 -->
    <section v-else class="compose-stage session-stage">
      <div class="compose-main">
        <div class="compose-title-row">
          <el-text tag="b">
            与 {{ counterpartyName }} 交易 · {{ session?.status_label_zh }}
          </el-text>
          <el-text size="small" type="info">
            {{ filledSlotCount }}/{{ maxLines }} ·
            {{ iAmLocked ? '已锁定' : '未锁定' }} ·
            {{ iAmConfirmed ? '已确认' : '未确认' }}
          </el-text>
        </div>

        <label class="field-label">道具（点空开背包 · 点满移除）</label>
        <div class="attach-rail slot-4x4">
          <button
            v-for="(slot, idx) in offerSlots"
            :key="idx"
            type="button"
            class="attach-slot"
            :class="{ filled: !!slot, disabled: !canDraft && !slot }"
            :title="slot ? `${slot.name} ×${slot.quantity}（点击移除）` : '空栏 · 从背包放入'"
            :disabled="!canDraft && !slot"
            @click="slot ? clearSlot(idx) : openBag()"
          >
            <template v-if="slot">
              <span class="slot-name">{{ slot.name }}</span>
              <span class="slot-qty">×{{ slot.quantity }}</span>
            </template>
            <span v-else class="slot-empty">空</span>
          </button>
        </div>

        <div class="money-send-row">
          <div class="stones-field">
            <el-text size="small">灵石</el-text>
            <el-input-number
              v-model="offerStones"
              :min="0"
              :step="1"
              :precision="0"
              size="small"
              controls-position="right"
              :disabled="!canDraft"
            />
          </div>
        </div>

        <div v-if="canDraft" class="vessel-row">
          <el-checkbox
            v-model="vesselOfferEnabled"
            :disabled="!canOfferVessel && !vesselOfferEnabled"
          >
            {{ vesselCtx?.can_offer_extend ? '延长炉鼎时限' : '愿为对方炉鼎' }}
          </el-checkbox>
          <el-input-number
            v-model="vesselHours"
            :min="0"
            :max="vesselCtx?.vessel_max_hours || 720"
            :step="1"
            :precision="0"
            size="small"
            :disabled="!vesselOfferEnabled"
            :controls="false"
          />
          <el-text size="small" type="info">现实小时</el-text>
        </div>
        <el-text v-if="canDraft" size="small" type="info">{{ vesselOfferHint }}</el-text>

        <div class="peer-offer-block">
          <el-text tag="b" size="small">对方报价</el-text>
          <el-text size="small">{{ formatOffer(theirOffer) }}</el-text>
          <div class="form-row">
            <el-tag size="small" :type="theyLocked ? 'warning' : 'info'">
              {{ theyLocked ? '已锁定' : '未锁定' }}
            </el-tag>
            <el-tag size="small" :type="theyConfirmed ? 'success' : 'info'">
              {{ theyConfirmed ? '已确认' : '未确认' }}
            </el-tag>
          </div>
        </div>

        <div v-if="canAct" class="form-row actions">
          <el-button
            type="warning"
            size="small"
            :loading="busy"
            :disabled="!canLock"
            @click="onLock"
          >
            锁定交易
          </el-button>
          <el-button
            type="primary"
            size="small"
            :loading="busy"
            :disabled="!canConfirm"
            @click="onConfirm"
          >
            确认成交
          </el-button>
          <el-button size="small" type="danger" plain :loading="busy" @click="onCancel">
            取消
          </el-button>
        </div>
      </div>

      <aside class="compose-side">
        <el-button size="small" type="primary" plain :disabled="!canDraft" @click="openBag">
          背包
        </el-button>
        <el-button size="small" :loading="busy" @click="onRefresh">刷新</el-button>
      </aside>
    </section>

    <el-dialog
      v-model="pickDialogVisible"
      :title="pickDialogTitle"
      width="360px"
      destroy-on-close
    >
      <el-empty v-if="!pickList.length" description="暂无可选" :image-size="48" />
      <div v-else class="pick-list">
        <button
          v-for="t in pickList"
          :key="t.character_id"
          type="button"
          class="pick-row"
          @click="pickTarget(t)"
        >
          <el-text tag="b" size="small">{{ t.name }}</el-text>
          <el-text size="small" type="info">
            {{ t.role_label_zh || '' }}
            {{ t.online ? '· 在线' : '· 离线' }}
          </el-text>
        </button>
      </div>
    </el-dialog>

    <el-dialog v-model="bagVisible" title="背包 · 可交易" width="420px" destroy-on-close>
      <el-empty v-if="!tradableBag.length" description="暂无可交易物品" :image-size="48" />
      <div v-else class="bag-grid">
        <button
          v-for="it in tradableBag"
          :key="it.item_uid"
          type="button"
          class="bag-cell"
          :disabled="bagItemDisabled(it)"
          @click="onBagCellClick(it, $event)"
        >
          <span class="slot-name">{{ it.name || it.item_id }}</span>
          <span class="slot-qty">×{{ it.quantity }}</span>
        </button>
      </div>
    </el-dialog>

    <Teleport to="body">
      <div
        v-if="qtyPopover.visible"
        class="qty-pop"
        :style="{ left: `${qtyPopover.left}px`, top: `${qtyPopover.top}px` }"
        @click.stop
      >
        <el-text size="small">数量</el-text>
        <el-input-number
          v-model="qtyPopover.quantity"
          :min="1"
          :max="qtyPopover.maxQty"
          size="small"
          controls-position="right"
        />
        <div class="qty-actions">
          <el-button size="small" @click="qtyPopover.visible = false">取消</el-button>
          <el-button type="primary" size="small" @click="confirmQty">放入</el-button>
        </div>
      </div>
    </Teleport>
  </el-card>
</template>

<style scoped>
.hdr {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.5rem;
}
.hint {
  margin-bottom: 0.75rem;
}
.compose-stage {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 108px;
  gap: 0.75rem;
  padding: 0.85rem;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: linear-gradient(
    165deg,
    var(--el-fill-color-blank) 0%,
    var(--el-fill-color-light) 100%
  );
}
.compose-main {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
}
.compose-title-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 0.25rem;
}
.field-label {
  font-size: 0.75rem;
  color: var(--el-text-color-secondary);
  margin-top: 0.2rem;
}
.compose-side {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
.invite-btn {
  margin-top: 0.5rem;
  align-self: flex-start;
}
.pending-box {
  margin-bottom: 0.75rem;
  padding: 0.65rem 0.75rem;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}
.pending-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 0.4rem;
}
.pending-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.attach-rail.slot-4x4 {
  display: grid;
  grid-template-columns: repeat(4, 72px);
  gap: 0.4rem;
  margin: 0.15rem 0 0.35rem;
}
.attach-slot {
  width: 72px;
  height: 72px;
  min-height: 72px;
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.03);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.15rem;
  padding: 0.35rem;
}
.attach-slot:hover {
  border-color: var(--el-color-primary-light-5);
}
.attach-slot.filled {
  border-style: solid;
  border-color: var(--el-color-primary-light-5);
  background: var(--el-fill-color-blank);
}
.attach-slot.disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.slot-name {
  font-size: 0.7rem;
  line-height: 1.2;
  text-align: center;
  word-break: break-all;
  max-height: 2.4em;
  overflow: hidden;
}
.slot-qty {
  font-size: 0.7rem;
  color: var(--el-text-color-secondary);
}
.slot-empty {
  font-size: 0.75rem;
  color: var(--el-text-color-placeholder);
}
.money-send-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  margin-top: 0.25rem;
}
.stones-field {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.vessel-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 0.35rem;
}
.session-meta {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-bottom: 0.75rem;
}
.form-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  margin-top: 0.5rem;
}
.peer-offer-block {
  margin-top: 0.75rem;
  padding-top: 0.5rem;
  border-top: 1px dashed var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.pick-list {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  max-height: 320px;
  overflow: auto;
}
.pick-row {
  text-align: left;
  border: 1px solid var(--el-border-color-lighter);
  background: transparent;
  border-radius: 6px;
  padding: 0.45rem 0.55rem;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
}
.bag-grid {
  display: grid;
  grid-template-columns: repeat(4, 72px);
  gap: 0.4rem;
}
.bag-cell {
  aspect-ratio: 1;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: var(--el-fill-color-blank);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.15rem;
  padding: 0.3rem;
}
.bag-cell:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.qty-pop {
  position: fixed;
  z-index: 4000;
  background: var(--el-bg-color-overlay);
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 0.6rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  box-shadow: var(--el-box-shadow-light);
}
.qty-actions {
  display: flex;
  gap: 0.35rem;
  justify-content: flex-end;
}
@media (max-width: 640px) {
  .compose-stage {
    grid-template-columns: 1fr;
  }
  .compose-side {
    flex-direction: row;
    flex-wrap: wrap;
  }
}
</style>
