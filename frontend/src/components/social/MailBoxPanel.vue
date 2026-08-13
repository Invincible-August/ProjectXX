<script setup lang="ts">
/**
 * 邮箱：收件箱 + 魔兽风写信台（右侧快捷选人 / 附件栏 / 背包点选入栏）。
 */
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useInventoryStore } from '../../stores/inventory'
import { useMailStore } from '../../stores/mail'
import type { InventoryItem } from '../../types/inventory'
import type { MailComposeTarget, MailItem } from '../../types/mail'
import { parseNonNegInt } from '../../utils/intMoney'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

type AttachSlot = {
  item_id: string
  name: string
  quantity: number
  max_stack: number
  bag_have: number
} | null

type PickKind = 'friend' | 'sect' | 'disciple'

const route = useRoute()
const mailStore = useMailStore()
const inventoryStore = useInventoryStore()
const busy = ref(false)
const loadError = ref('')
const selected = ref<MailItem | null>(null)

/** 写信表单 */
const toName = ref('')
const subjectZh = ref('')
const bodyZh = ref('')
const spiritStones = ref(0)

/** 固定附件栏（空槽占位，魔兽风） */
const attachSlots = ref<AttachSlot[]>([])

/** 右侧弹窗：选人 */
const pickDialogVisible = ref(false)
const pickKind = ref<PickKind>('friend')

/** 背包窗 */
const bagVisible = ref(false)

/** 堆叠数量浮层（附着在点击的背包格上） */
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

const maxLines = computed(
  () =>
    Number(
      mailStore.limits?.max_attachment_lines ??
        mailStore.composeOptions?.limits?.max_attachment_lines ??
        6,
    ),
)

const tradableBag = computed(() =>
  inventoryStore.normalItems.filter((x) => x.tradable && !x.bound),
)

const pickDialogTitle = computed(() => {
  if (pickKind.value === 'sect') return '选择同门'
  if (pickKind.value === 'disciple') return '选择弟子'
  return '选择道友'
})

const pickList = computed((): MailComposeTarget[] => {
  const opts = mailStore.composeOptions
  if (!opts) return []
  if (pickKind.value === 'sect') return opts.sect_members
  if (pickKind.value === 'disciple') return opts.disciples
  return opts.friends
})

const filledAttachCount = computed(
  () => attachSlots.value.filter((s) => s != null).length,
)

function ensureSlotGrid(): void {
  const n = maxLines.value
  const next: AttachSlot[] = Array.from({ length: n }, (_, i) => attachSlots.value[i] ?? null)
  attachSlots.value = next
}

onMounted(async () => {
  loadError.value = ''
  const prefill = route.query.to
  if (typeof prefill === 'string' && prefill.trim()) {
    toName.value = prefill.trim()
  }
  const [errMail, errOpt, errInv] = await Promise.all([
    mailStore.refresh(),
    mailStore.loadComposeOptions(),
    inventoryStore.load(),
  ])
  ensureSlotGrid()
  const firstErr = errMail || errOpt || errInv
  if (firstErr) {
    loadError.value = firstErr
    emit('log', firstErr, 'warning')
  }
  document.addEventListener('click', onDocClickCloseQty, true)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocClickCloseQty, true)
})

function onDocClickCloseQty(ev: MouseEvent): void {
  if (!qtyPopover.value.visible) return
  const t = ev.target as HTMLElement | null
  if (t?.closest?.('.qty-float') || t?.closest?.('.bag-cell')) return
  closeQtyPopover()
}

function selectMail(row: MailItem): void {
  selected.value = row
  if (!row.is_read) {
    void mailStore.markRead(row.id).then((err) => {
      if (err) emit('log', err, 'warning')
    })
  }
}

function openPickDialog(kind: PickKind): void {
  pickKind.value = kind
  pickDialogVisible.value = true
}

function pickTarget(name: string): void {
  toName.value = name
  pickDialogVisible.value = false
  ElMessage.success(`收件人：${name}`)
}

async function openBag(): Promise<void> {
  closeQtyPopover()
  const err = await inventoryStore.load()
  if (err) {
    ElMessage.error(err)
    emit('log', err, 'warning')
    return
  }
  bagVisible.value = true
}

function closeQtyPopover(): void {
  qtyPopover.value = {
    visible: false,
    left: 0,
    top: 0,
    item: null,
    quantity: 1,
    maxQty: 1,
  }
}

/**
 * 点击背包格：可堆叠弹出数量窗；数量为 1 则直接入栏。
 */
function onBagCellClick(item: InventoryItem, ev: MouseEvent): void {
  ev.stopPropagation()
  const have = Math.max(0, Number(item.quantity ?? 0))
  if (have <= 0) {
    ElMessage.warning('数量不足')
    return
  }
  const maxStack = Math.max(1, Number(item.max_stack ?? 99))
  const maxQty = Math.min(have, maxStack)
  // 已在栏中：改为调整数量（仍走浮层）
  const existingIdx = attachSlots.value.findIndex((s) => s?.item_id === item.item_id)
  if (have === 1 && maxStack === 1 && existingIdx < 0) {
    putIntoSlot(item, 1)
    return
  }
  const el = ev.currentTarget as HTMLElement
  const rect = el.getBoundingClientRect()
  qtyPopover.value = {
    visible: true,
    left: Math.min(rect.left, window.innerWidth - 180),
    top: Math.min(rect.bottom + 4, window.innerHeight - 120),
    item,
    quantity: existingIdx >= 0 ? (attachSlots.value[existingIdx]?.quantity ?? 1) : 1,
    maxQty,
  }
}

function confirmQty(): void {
  const pop = qtyPopover.value
  if (!pop.item) return
  const qty = Math.max(1, Math.min(Number(pop.quantity) || 1, pop.maxQty))
  putIntoSlot(pop.item, qty)
  closeQtyPopover()
}

function putIntoSlot(item: InventoryItem, quantity: number): void {
  ensureSlotGrid()
  const maxStack = Math.max(1, Number(item.max_stack ?? 99))
  const have = Math.max(0, Number(item.quantity ?? 0))
  const qty = Math.max(1, Math.min(quantity, have, maxStack))
  const existingIdx = attachSlots.value.findIndex((s) => s?.item_id === item.item_id)
  if (existingIdx >= 0) {
    const cur = attachSlots.value[existingIdx]
    if (cur) {
      attachSlots.value[existingIdx] = {
        ...cur,
        quantity: qty,
        bag_have: have,
      }
    }
    ElMessage.success(`已更新「${item.name}」×${qty}`)
    return
  }
  const emptyIdx = attachSlots.value.findIndex((s) => s == null)
  if (emptyIdx < 0) {
    ElMessage.warning(`附件栏已满（最多 ${maxLines.value} 种）`)
    return
  }
  attachSlots.value[emptyIdx] = {
    item_id: item.item_id,
    name: item.name,
    quantity: qty,
    max_stack: maxStack,
    bag_have: have,
  }
  ElMessage.success(`已放入「${item.name}」×${qty}`)
}

function clearSlot(idx: number): void {
  if (!attachSlots.value[idx]) return
  attachSlots.value[idx] = null
}

function attachLinesPayload(): Array<{ item_id: string; quantity: number }> {
  return attachSlots.value
    .filter((s): s is NonNullable<AttachSlot> => s != null)
    .map((s) => ({ item_id: s.item_id, quantity: s.quantity }))
}

function resetComposeAttach(): void {
  attachSlots.value = Array.from({ length: maxLines.value }, () => null)
  spiritStones.value = 0
}

async function onClaim(row: MailItem): Promise<void> {
  if (busy.value || !row.can_claim) return
  busy.value = true
  try {
    const err = await mailStore.claim(row.id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(mailStore.lastMessage || '附件已入包')
    emit('log', mailStore.lastMessage || '已领取附件', 'success')
    selected.value = mailStore.items.find((m) => m.id === row.id) ?? null
  } finally {
    busy.value = false
  }
}

async function onDelete(row: MailItem): Promise<void> {
  if (busy.value || !row.can_delete) return
  busy.value = true
  try {
    const err = await mailStore.remove(row.id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(mailStore.lastMessage || '已删除')
    emit('log', mailStore.lastMessage || '已删除邮件', 'info')
    selected.value = null
  } finally {
    busy.value = false
  }
}

async function onClaimAll(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await mailStore.claimAll()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(mailStore.lastMessage || '已领取')
    emit('log', mailStore.lastMessage || '一键领取完成', 'success')
    selected.value = null
  } finally {
    busy.value = false
  }
}

async function onReadAll(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await mailStore.markReadAll()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(mailStore.lastMessage || '已全部标读')
    emit('log', mailStore.lastMessage || '一键已读完成', 'info')
  } finally {
    busy.value = false
  }
}

async function onDeleteAll(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await mailStore.removeAllEligible()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(mailStore.lastMessage || '已删除')
    emit('log', mailStore.lastMessage || '一键删除完成', 'info')
    selected.value = null
  } finally {
    busy.value = false
  }
}

async function onSend(broadcast: 'sect' | 'disciples' | null = null): Promise<void> {
  if (busy.value) return
  if (!broadcast && !toName.value.trim()) {
    ElMessage.warning('请填写或选择收件人道号')
    return
  }
  const stones = parseNonNegInt(spiritStones.value)
  if (stones === null) {
    ElMessage.warning('灵石须为 ≥ 0 的整数')
    return
  }
  busy.value = true
  try {
    const err = await mailStore.sendPlayerMail({
      to_name: broadcast ? undefined : toName.value.trim(),
      subject_zh: subjectZh.value,
      body_zh: bodyZh.value,
      spirit_stones: stones,
      items: attachLinesPayload(),
      broadcast,
    })
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(mailStore.lastMessage || '已送信')
    emit('log', mailStore.lastMessage || '已送信', 'success')
    bodyZh.value = ''
    subjectZh.value = ''
    resetComposeAttach()
    if (!broadcast) toName.value = ''
    await inventoryStore.load()
    await nextTick()
  } finally {
    busy.value = false
  }
}

function attachSummary(row: MailItem): string {
  if (!row.has_attachments) return '无附件'
  const parts: string[] = []
  const stones = Number(row.attachments?.spirit_stones ?? 0)
  if (stones > 0) parts.push(`${stones} 灵石`)
  for (const line of row.attachments?.items ?? []) {
    parts.push(`${line.item_id}×${line.quantity}`)
  }
  return parts.join(' · ') || '有附件'
}

function bagCellDisabled(item: InventoryItem): boolean {
  const inSlot = attachSlots.value.some((s) => s?.item_id === item.item_id)
  if (inSlot) return false
  return filledAttachCount.value >= maxLines.value
}
</script>

<template>
  <el-card shadow="never" class="mail-panel">
    <template #header>
      <div class="hdr">
        <el-text tag="b">邮箱</el-text>
        <el-text size="small" type="info">未读 {{ mailStore.unread }}</el-text>
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

    <div class="batch-bar">
      <el-button size="small" type="primary" :loading="busy" @click="onClaimAll">
        一键领取
      </el-button>
      <el-button size="small" :loading="busy" @click="onReadAll">一键已读</el-button>
      <el-button size="small" type="danger" plain :loading="busy" @click="onDeleteAll">
        一键删除
      </el-button>
      <el-text size="small" type="info">删除仅限已读且附件已领</el-text>
    </div>

    <!-- 收件箱 -->
    <section class="inbox-block">
      <div class="mail-grid">
        <div class="mail-list">
          <el-empty
            v-if="!mailStore.items.length"
            description="暂无邮件"
            :image-size="48"
          />
          <button
            v-for="row in mailStore.items"
            :key="row.id"
            type="button"
            class="mail-row"
            :class="{ active: selected?.id === row.id, unread: !row.is_read }"
            @click="selectMail(row)"
          >
            <div class="row-top">
              <el-text size="small" type="info">{{ row.mail_kind_label_zh }}</el-text>
              <el-text tag="b" size="small">{{ row.subject_zh }}</el-text>
            </div>
            <el-text size="small" truncated>
              {{ row.from_name }} · {{ attachSummary(row) }}
            </el-text>
          </button>
        </div>

        <div v-if="selected" class="mail-detail">
          <el-text tag="b">{{ selected.subject_zh }}</el-text>
          <el-text size="small" type="info" class="meta">
            来自 {{ selected.from_name }} · {{ selected.mail_kind_label_zh }}
          </el-text>
          <p class="body">{{ selected.body_zh }}</p>
          <el-text size="small">附件：{{ attachSummary(selected) }}</el-text>
          <div class="actions">
            <el-button
              type="primary"
              size="small"
              :disabled="!selected.can_claim || busy"
              @click="onClaim(selected)"
            >
              领取附件
            </el-button>
            <el-button
              type="danger"
              size="small"
              plain
              :disabled="!selected.can_delete || busy"
              @click="onDelete(selected)"
            >
              删除
            </el-button>
          </div>
        </div>
        <el-empty v-else description="选择一封邮件查看" :image-size="48" />
      </div>
    </section>

    <!-- 写信台：主栏 + 右侧快捷轨 -->
    <section class="compose-stage">
      <div class="compose-main">
        <div class="compose-title-row">
          <el-text tag="b">写信</el-text>
          <el-text size="small" type="info">
            附物须可交易非绑定 · 栏位 {{ filledAttachCount }}/{{ maxLines }}
          </el-text>
        </div>

        <label class="field-label">收件人</label>
        <el-input
          v-model="toName"
          placeholder="道号（或右侧快捷选择）"
          size="small"
          clearable
        />

        <label class="field-label">标题</label>
        <el-input v-model="subjectZh" placeholder="请填写标题" size="small" clearable />

        <label class="field-label">正文</label>
        <el-input
          v-model="bodyZh"
          type="textarea"
          :rows="3"
          placeholder="正文 / 附言"
          size="small"
          resize="none"
        />

        <label class="field-label">附件</label>
        <div class="attach-rail" :style="{ '--slot-count': maxLines }">
          <button
            v-for="(slot, idx) in attachSlots"
            :key="idx"
            type="button"
            class="attach-slot"
            :class="{ filled: !!slot }"
            :title="slot ? `${slot.name} ×${slot.quantity}（点击清空）` : '空栏 · 从背包放入'"
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
            <el-text size="small">附带灵石</el-text>
            <el-input-number
              v-model="spiritStones"
              :min="0"
              :step="1"
              :precision="0"
              size="small"
              controls-position="right"
            />
          </div>
          <el-button type="primary" :loading="busy" @click="onSend(null)">送信</el-button>
        </div>
      </div>

      <aside class="compose-side">
        <el-button size="small" @click="openPickDialog('friend')">道友</el-button>
        <el-button size="small" @click="openPickDialog('sect')">宗门</el-button>
        <el-button size="small" @click="openPickDialog('disciple')">弟子</el-button>
        <el-button size="small" type="primary" plain @click="openBag">背包</el-button>
        <div class="side-divider" />
        <el-button
          size="small"
          type="warning"
          plain
          :disabled="!mailStore.composeOptions?.can_sect_broadcast || busy"
          @click="onSend('sect')"
        >
          宗门群发
        </el-button>
        <el-button
          size="small"
          type="warning"
          plain
          :disabled="!mailStore.composeOptions?.can_disciple_broadcast || busy"
          @click="onSend('disciples')"
        >
          弟子群发
        </el-button>
      </aside>
    </section>

    <!-- 选人弹窗 -->
    <el-dialog
      v-model="pickDialogVisible"
      :title="pickDialogTitle"
      width="420px"
      destroy-on-close
      append-to-body
    >
      <el-empty
        v-if="!pickList.length"
        description="暂无可选名单"
        :image-size="48"
      />
      <div v-else class="pick-grid">
        <button
          v-for="t in pickList"
          :key="t.character_id"
          type="button"
          class="pick-card"
          @click="pickTarget(t.name)"
        >
          <el-text tag="b">{{ t.name }}</el-text>
          <el-text v-if="t.rank_label_zh" size="small" type="info">
            {{ t.rank_label_zh }}
          </el-text>
        </button>
      </div>
    </el-dialog>

    <!-- 背包窗：点选入附件栏 -->
    <el-dialog
      v-model="bagVisible"
      title="背包 · 点选可交易物品放入附件栏"
      width="520px"
      destroy-on-close
      append-to-body
      @closed="closeQtyPopover"
    >
      <el-text size="small" type="info" class="bag-hint">
        仅可放入可交易、非绑定物品。可堆叠物品会弹出数量；再点同一物品可改数量。
      </el-text>
      <el-empty
        v-if="!tradableBag.length"
        description="暂无可附物品"
        :image-size="48"
      />
      <div v-else class="bag-grid">
        <button
          v-for="item in tradableBag"
          :key="item.item_uid"
          type="button"
          class="bag-cell"
          :class="{
            'in-slot': attachSlots.some((s) => s?.item_id === item.item_id),
            disabled: bagCellDisabled(item),
          }"
          :disabled="bagCellDisabled(item)"
          @click="onBagCellClick(item, $event)"
        >
          <span class="bag-cell-name">{{ item.name }}</span>
          <span class="bag-cell-qty">×{{ item.quantity }}</span>
        </button>
      </div>
    </el-dialog>

    <!-- 堆叠数量浮层：附着在点击格下方 -->
    <Teleport to="body">
      <div
        v-if="qtyPopover.visible && qtyPopover.item"
        class="qty-float"
        :style="{ left: `${qtyPopover.left}px`, top: `${qtyPopover.top}px` }"
        @click.stop
      >
        <el-text size="small" tag="b">{{ qtyPopover.item.name }}</el-text>
        <el-text size="small" type="info">最多 {{ qtyPopover.maxQty }}</el-text>
        <el-input-number
          v-model="qtyPopover.quantity"
          :min="1"
          :max="qtyPopover.maxQty"
          size="small"
          controls-position="right"
        />
        <div class="qty-actions">
          <el-button size="small" @click="closeQtyPopover">取消</el-button>
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
  align-items: center;
}
.hint {
  margin-bottom: 0.75rem;
}
.batch-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: center;
  margin-bottom: 0.75rem;
}
.inbox-block {
  margin-bottom: 1rem;
}
.mail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr);
  gap: 0.75rem;
}
.mail-list {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  max-height: 280px;
  overflow: auto;
}
.mail-row {
  text-align: left;
  border: 1px solid var(--el-border-color-lighter);
  background: transparent;
  border-radius: 6px;
  padding: 0.45rem 0.55rem;
  cursor: pointer;
}
.mail-row.unread {
  border-color: var(--el-color-primary-light-5);
}
.mail-row.active {
  background: var(--el-fill-color-light);
}
.row-top {
  display: flex;
  gap: 0.4rem;
  align-items: baseline;
  margin-bottom: 0.15rem;
}
.mail-detail {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.meta {
  display: block;
}
.body {
  white-space: pre-wrap;
  margin: 0.25rem 0;
  font-size: 0.9rem;
}
.actions {
  margin-top: 0.35rem;
  display: flex;
  gap: 0.4rem;
}

/* —— 写信台 —— */
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
.attach-rail {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(72px, 1fr));
  gap: 0.4rem;
  margin: 0.15rem 0 0.35rem;
}
.attach-slot {
  aspect-ratio: 1;
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
  transition: border-color 0.15s ease, background 0.15s ease;
}
.attach-slot:hover {
  border-color: var(--el-color-primary-light-5);
}
.attach-slot.filled {
  border-style: solid;
  border-color: var(--el-color-primary-light-3);
  background: var(--el-color-primary-light-9);
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
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--el-color-primary);
}
.slot-empty {
  font-size: 0.75rem;
  color: var(--el-text-color-placeholder);
}
.money-send-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.35rem;
}
.stones-field {
  display: flex;
  align-items: center;
  gap: 0.45rem;
}
.compose-side {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  align-items: stretch;
}
.compose-side :deep(.el-button) {
  margin: 0;
}
.side-divider {
  height: 1px;
  background: var(--el-border-color-lighter);
  margin: 0.15rem 0;
}

.pick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 0.5rem;
}
.pick-card {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  align-items: flex-start;
  text-align: left;
  padding: 0.55rem 0.65rem;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
}
.pick-card:hover {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-fill-color-light);
}

.bag-hint {
  display: block;
  margin-bottom: 0.65rem;
}
.bag-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 0.45rem;
  max-height: 360px;
  overflow: auto;
}
.bag-cell {
  position: relative;
  min-height: 64px;
  padding: 0.4rem;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: var(--el-fill-color-blank);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.2rem;
  text-align: left;
}
.bag-cell:hover:not(.disabled) {
  border-color: var(--el-color-primary);
}
.bag-cell.in-slot {
  border-color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}
.bag-cell.disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.bag-cell-name {
  font-size: 0.75rem;
  line-height: 1.25;
  word-break: break-all;
}
.bag-cell-qty {
  font-size: 0.8rem;
  font-weight: 600;
  align-self: flex-end;
}

@media (max-width: 720px) {
  .mail-grid,
  .compose-stage {
    grid-template-columns: 1fr;
  }
  .compose-side {
    flex-direction: row;
    flex-wrap: wrap;
  }
}
</style>

<style>
/* 浮层挂到 body，非 scoped */
.qty-float {
  position: fixed;
  z-index: 4000;
  min-width: 160px;
  padding: 0.55rem 0.65rem;
  border-radius: 8px;
  border: 1px solid var(--el-border-color);
  background: var(--el-bg-color-overlay, #fff);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.qty-float .qty-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.35rem;
}
</style>
