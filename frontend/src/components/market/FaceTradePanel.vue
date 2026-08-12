<script setup lang="ts">
/**
 * 面交面板：双栏报价 / 背包挑选 / 接受·锁定·确认·取消；会话活跃时轮询。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useInventoryStore } from '../../stores/inventory'
import { useTradeStore } from '../../stores/trade'
import type { TradeItemLine } from '../../types/trade'

const props = defineProps<{
  /** 路由 query.peer：角色 id 或道号预填 */
  peer?: string | null
  /** 已有会话 id（可选深链） */
  sessionId?: number | null
}>()

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
  /** 会话 id 变化，便于父级写入 query */
  'session-change': [sessionId: number | null]
}>()

const tradeStore = useTradeStore()
const inventoryStore = useInventoryStore()
const busy = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null

/** 邀请对方道号 */
const peerName = ref('')
/** 草稿灵石 */
const offerStones = ref(0)
/** 本地草稿物品行（点选背包写入，提交前可再编辑） */
const draftItems = ref<TradeItemLine[]>([])

const session = computed(() => tradeStore.faceSession)

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
const canDraft = computed(() => {
  const st = session.value?.status
  if (!st || !canAct.value) return false
  if (iAmLocked.value) return false
  return st === 'browsing' || (st === 'locking' && !iAmLocked.value)
})
const canLock = computed(
  () => canAct.value && (session.value?.status === 'browsing' || session.value?.status === 'locking') && !iAmLocked.value,
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

/** 普通袋可交易物（非绑定） */
const tradableBag = computed(() =>
  inventoryStore.normalItems.filter((x) => x.tradable !== false && !x.bound),
)

/**
 * 解析 peer 预填：纯数字视为角色 id，否则当道号。
 */
function applyPeerPrefill(raw: string | null | undefined): void {
  const v = (raw || '').trim()
  if (!v) return
  if (/^\d+$/.test(v)) {
    peerName.value = ''
  } else {
    peerName.value = v
  }
}

function syncDraftFromSession(): void {
  const offer = myOffer.value
  if (!offer) {
    draftItems.value = []
    offerStones.value = 0
    return
  }
  draftItems.value = (offer.items ?? []).map((l) => ({
    item_id: l.item_id,
    quantity: l.quantity,
  }))
  offerStones.value = Number(offer.spirit_stones) || 0
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
  await inventoryStore.load()
  if (props.sessionId && props.sessionId > 0) {
    const err = await tradeStore.loadFace(props.sessionId)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
    } else if (tradeStore.faceSession) {
      emit('session-change', tradeStore.faceSession.id)
      syncDraftFromSession()
      startPolling()
    }
  }
})

onUnmounted(() => {
  stopPolling()
})

watch(
  () => props.peer,
  (v) => applyPeerPrefill(v),
)

watch(
  () => session.value?.id,
  (id) => {
    emit('session-change', id ?? null)
    if (id && canAct.value) {
      startPolling()
    } else {
      stopPolling()
    }
  },
)

watch(
  () => session.value?.version,
  () => {
    if (!iAmLocked.value) {
      syncDraftFromSession()
    }
  },
)

async function onInvite(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const peerRaw = (props.peer || '').trim()
    let err: string | null
    if (peerRaw && /^\d+$/.test(peerRaw) && !peerName.value.trim()) {
      err = await tradeStore.inviteFace({
        peer_character_id: Number(peerRaw),
      })
    } else {
      const name = peerName.value.trim()
      if (!name) {
        ElMessage.warning('请输入对方道号')
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
    ElMessage.success(tradeStore.lastMessage || '已发起面交')
    emit('log', tradeStore.lastMessage || '面交已发起', 'success')
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

/**
 * 从背包点选一件加入草稿（同 id 累加数量）。
 */
function addFromBag(itemId: string): void {
  if (!canDraft.value) return
  const existing = draftItems.value.find((x) => x.item_id === itemId)
  if (existing) {
    existing.quantity += 1
  } else {
    draftItems.value.push({ item_id: itemId, quantity: 1 })
  }
}

function removeDraftLine(index: number): void {
  if (!canDraft.value) return
  draftItems.value.splice(index, 1)
}

async function onSetOffer(): Promise<void> {
  if (busy.value || !canDraft.value) return
  busy.value = true
  try {
    const err = await tradeStore.setFaceOffer(
      draftItems.value.map((l) => ({
        item_id: l.item_id,
        quantity: Number(l.quantity) || 1,
      })),
      Number(offerStones.value) || 0,
    )
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(tradeStore.lastMessage || '草稿已更新')
    emit('log', tradeStore.lastMessage || '面交草稿已更新', 'success')
  } finally {
    busy.value = false
  }
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
    await inventoryStore.load()
    ElMessage.success(tradeStore.lastMessage || '已接受')
    emit('log', tradeStore.lastMessage || '面交已接受', 'success')
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
    ElMessage.success(tradeStore.lastMessage || '已拒绝')
    emit('log', tradeStore.lastMessage || '面交已拒绝', 'info')
  } finally {
    busy.value = false
  }
}

async function onLock(): Promise<void> {
  if (busy.value || !canLock.value) return
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
    emit('log', tradeStore.lastMessage || '面交已锁定', 'success')
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
    emit('log', tradeStore.lastMessage || '面交确认', 'success')
    if (session.value?.status === 'committed') {
      stopPolling()
    }
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
    emit('log', tradeStore.lastMessage || '面交已取消', 'info')
  } finally {
    busy.value = false
  }
}

function formatOffer(
  offer: { items: { item_id: string; quantity: number }[]; spirit_stones: number } | null,
): string {
  if (!offer) return '—'
  const parts = (offer.items ?? []).map((l) => `${l.item_id}×${l.quantity}`)
  if (offer.spirit_stones) parts.push(`${offer.spirit_stones} 灵石`)
  return parts.length ? parts.join('、') : '（空）'
}
</script>

<template>
  <el-card shadow="never" class="face-panel">
    <template #header>
      <el-text tag="b">当面交易</el-text>
    </template>

    <div v-if="!session" class="invite-block">
      <div class="form-row">
        <el-input
          v-model="peerName"
          placeholder="对方道号"
          size="small"
          clearable
          style="max-width: 200px"
          @keyup.enter="onInvite"
        />
        <el-button type="primary" size="small" :loading="busy" @click="onInvite">
          发起面交
        </el-button>
      </div>
      <el-text v-if="peer && /^\d+$/.test(peer)" size="small" type="warning">
        将按角色 id={{ peer }} 邀请（也可改填道号）
      </el-text>
    </div>

    <template v-else>
      <div class="session-meta">
        <el-text tag="b">
          会话 #{{ session.id }} · {{ session.status_label_zh }}
        </el-text>
        <el-text size="small" type="info">
          {{ session.initiator_name }} ⇄ {{ session.peer_name }} · v{{ session.version }}
          · 对方{{ session.peer_online ? '在线' : '离线' }}
        </el-text>
        <el-text v-if="session.expires_at" size="small" type="warning">
          超时 {{ session.expires_at }}
        </el-text>
        <el-button size="small" :loading="busy" @click="onRefresh">刷新</el-button>
      </div>

      <div
        v-if="isPendingInvite && isPeerViewer"
        class="form-row pending-actions"
      >
        <el-button type="primary" size="small" :loading="busy" @click="onAccept">
          接受
        </el-button>
        <el-button size="small" type="danger" plain :loading="busy" @click="onReject">
          拒绝
        </el-button>
      </div>
      <el-alert
        v-else-if="isPendingInvite"
        title="等待对方接受邀约…"
        type="info"
        :closable="false"
        show-icon
        class="hint"
      />

      <div v-if="!isPendingInvite || !isPeerViewer" class="trade-columns">
        <div class="col bag-col">
          <el-text size="small" type="info">我的背包（可交易）</el-text>
          <div v-if="tradableBag.length === 0" class="muted">暂无可交易物品</div>
          <div v-else class="bag-list">
            <button
              v-for="it in tradableBag"
              :key="it.item_uid"
              type="button"
              class="bag-item"
              :disabled="!canDraft"
              @click="addFromBag(it.item_id)"
            >
              {{ it.name || it.item_id }} ×{{ it.quantity }}
            </button>
          </div>
        </div>

        <div class="col offer-col">
          <el-text size="small" type="info">我的报价</el-text>
          <div class="offer-body">{{ formatOffer(myOffer) }}</div>
          <el-tag size="small" :type="iAmLocked ? 'warning' : 'info'">
            {{ iAmLocked ? '已锁定' : '未锁定' }}
          </el-tag>
          <el-tag size="small" :type="iAmConfirmed ? 'success' : 'info'" class="tag-gap">
            {{ iAmConfirmed ? '已确认' : '未确认' }}
          </el-tag>

          <template v-if="canDraft">
            <div class="draft-lines">
              <div
                v-for="(line, idx) in draftItems"
                :key="`${line.item_id}-${idx}`"
                class="draft-line"
              >
                <span>{{ line.item_id }}</span>
                <el-input-number
                  v-model="line.quantity"
                  :min="1"
                  size="small"
                  controls-position="right"
                />
                <el-button size="small" text type="danger" @click="removeDraftLine(idx)">
                  移除
                </el-button>
              </div>
            </div>
            <div class="form-row">
              <el-text size="small">灵石</el-text>
              <el-input-number
                v-model="offerStones"
                :min="0"
                size="small"
                :controls="false"
              />
              <el-button size="small" :loading="busy" @click="onSetOffer">
                更新草稿
              </el-button>
            </div>
          </template>
        </div>

        <div class="col offer-col">
          <el-text size="small" type="info">对方报价</el-text>
          <div class="offer-body">{{ formatOffer(theirOffer) }}</div>
          <el-tag size="small" :type="theyLocked ? 'warning' : 'info'">
            {{ theyLocked ? '已锁定' : '未锁定' }}
          </el-tag>
          <el-tag size="small" :type="theyConfirmed ? 'success' : 'info'" class="tag-gap">
            {{ theyConfirmed ? '已确认' : '未确认' }}
          </el-tag>
        </div>
      </div>

      <div v-if="canAct && !isPendingInvite" class="form-row actions">
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
      <el-alert
        v-else-if="!canAct"
        :title="`会话已结束：${session.status_label_zh}`"
        type="info"
        :closable="false"
        show-icon
        class="hint"
      />
    </template>
  </el-card>
</template>

<style scoped>
.invite-block {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  margin-top: 0.5rem;
}

.session-meta {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-bottom: 0.75rem;
}

.trade-columns {
  display: grid;
  grid-template-columns: 1.1fr 1fr 1fr;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.col {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
}

.bag-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  max-height: 180px;
  overflow: auto;
}

.bag-item {
  text-align: left;
  border: 1px solid var(--el-border-color);
  background: var(--el-fill-color-blank);
  border-radius: 4px;
  padding: 0.25rem 0.4rem;
  cursor: pointer;
  font-size: 12px;
}

.bag-item:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.offer-body {
  font-size: 13px;
  word-break: break-all;
}

.draft-lines {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-top: 0.35rem;
}

.draft-line {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: center;
  font-size: 12px;
}

.tag-gap {
  margin-left: 0.25rem;
}

.muted {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.hint {
  margin-top: 0.5rem;
}

.actions {
  margin-top: 0.25rem;
}

@media (max-width: 800px) {
  .trade-columns {
    grid-template-columns: 1fr;
  }
}
</style>
