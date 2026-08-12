<script setup lang="ts">
/**
 * 横切聊天坞：五频道消息流（含机缘）+ 发机缘表单；消息区可滚动，新内容自底部顶上。
 */
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useChatStore } from '../../stores/chat'
import { useHeritageStore } from '../../stores/heritage'
import { useInventoryStore } from '../../stores/inventory'
import type { ChatChannelItem, ChatMessageItem } from '../../types/chat'
import type { HeritagePacket } from '../../types/heritage'
import { chatNameColorByMajorRealm } from '../../utils/chatRealmNameColor'
import HeritageCard from './HeritageCard.vue'

/** 消息流统一行：聊天或机缘 */
type FeedRow =
  | { key: string; kind: 'chat'; at: number; message: ChatMessageItem }
  | { key: string; kind: 'heritage'; at: number; packet: HeritagePacket }

const router = useRouter()
const chatStore = useChatStore()
const heritageStore = useHeritageStore()
const inventoryStore = useInventoryStore()
const listEl = ref<HTMLElement | null>(null)
/** 是否贴底：用户上滑查看历史时不强制跳回底部 */
const stickToBottom = ref(true)

const sortedChannels = computed(() => {
  const order = ['world', 'sect', 'dm', 'mentor', 'party']
  return [...chatStore.channels].sort((a, b) => {
    const ia = order.indexOf(a.channel_type)
    const ib = order.indexOf(b.channel_type)
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib)
  })
})

/** 仅世界 / 宗门可发机缘 */
const canSendHeritage = computed(() => {
  const t = chatStore.activeChannel?.channel_type
  return (
    Boolean(chatStore.activeChannel?.can_send) &&
    (t === 'world' || t === 'sect')
  )
})

/**
 * 页签角标：私聊有未读只显示点（人数汇总在坞按钮）；其它频仍显示条数。
 */
function tabBadge(ch: ChatChannelItem): string | null {
  const n = Number(ch.unread) || 0
  if (n <= 0) return null
  if (ch.channel_type === 'dm') return '·'
  return String(n)
}

/**
 * 聊天 + 机缘时间线：旧在上、新在下（底部刷新向上顶）。
 * 机缘仅展示当前频道；私聊/队伍/师承不混入其它频红包。
 */
const feedRows = computed((): FeedRow[] => {
  const rows: FeedRow[] = []
  const channelRef = chatStore.activeChannelRef
  for (const m of chatStore.messages) {
    const at = Date.parse(String(m.created_at || '')) || Number(m.id) || 0
    rows.push({ key: `c-${m.id}`, kind: 'chat', at, message: m })
  }
  const channelType = chatStore.activeChannel?.channel_type
  const heritageAllowed = channelType === 'world' || channelType === 'sect'
  if (heritageAllowed && channelRef) {
    for (const p of heritageStore.packets) {
      if (String(p.channel_ref || '') !== channelRef) continue
      const at = Date.parse(String(p.created_at || '')) || Number(p.id) || 0
      rows.push({
        key: `h-${p.id}-${p.created_at || ''}`,
        kind: 'heritage',
        at,
        packet: p,
      })
    }
  }
  return rows.sort((a, b) => {
    if (a.at !== b.at) return a.at - b.at
    return a.key.localeCompare(b.key)
  })
})

/**
 * 切频时同步机缘：世界/宗门拉取本频；其它频清空可见列表，避免红包盖住聊天。
 */
watch(
  () => chatStore.activeChannelRef,
  (ref) => {
    const t = chatStore.activeChannel?.channel_type
    if (t === 'world' || t === 'sect') {
      void heritageStore.refresh(ref)
    } else {
      void heritageStore.refresh(null)
    }
  },
)

async function scrollBottom(force = false): Promise<void> {
  await nextTick()
  if (!listEl.value) return
  if (!force && !stickToBottom.value) return
  listEl.value.scrollTop = listEl.value.scrollHeight
}

/**
 * 滚动时判断是否仍贴近底部（允许上滑翻看历史）。
 */
function onListScroll(): void {
  const el = listEl.value
  if (!el) return
  const gap = el.scrollHeight - el.scrollTop - el.clientHeight
  stickToBottom.value = gap < 48
}

watch(
  () => feedRows.value.length,
  () => {
    void scrollBottom()
  },
)

watch(
  () => heritageStore.highlightId,
  () => {
    stickToBottom.value = true
    void scrollBottom(true)
  },
)

onUnmounted(() => {
  chatStore.stopPollingFallback()
})

function toggleDock(): void {
  if (chatStore.dockOpen) {
    chatStore.closeDock()
  } else {
    stickToBottom.value = true
    chatStore.openDock()
    void scrollBottom(true)
  }
}

async function onSelect(ch: ChatChannelItem): Promise<void> {
  if (!ch.can_access || !ch.channel_ref) {
    ElMessage.warning(ch.lock_reason_zh || '频道不可用')
    return
  }
  stickToBottom.value = true
  await chatStore.selectChannel(ch.channel_ref)
  void scrollBottom(true)
}

async function onSend(): Promise<void> {
  stickToBottom.value = true
  const err = await chatStore.send()
  if (err) ElMessage.error(err)
  else void scrollBottom(true)
}

/**
 * 道号按发言者大境界着色。
 *
 * @param m - 聊天消息
 */
function nameStyle(m: ChatMessageItem): { color: string } {
  return { color: chatNameColorByMajorRealm(m.sender_major_realm) }
}

/**
 * 机缘摘要。
 *
 * @param p - 机缘包
 */
function heritageSummary(p: HeritagePacket): string {
  const parts = [`${p.shares_claimed}/${p.share_count} 份`]
  if (Number(p.spirit_stones_total) > 0) {
    parts.unshift(`${p.spirit_stones_total} 灵石`)
  }
  for (const line of p.items || []) {
    parts.push(`${line.name || line.item_id}×${line.quantity}`)
  }
  if (p.status === 'exhausted') parts.push('已领完')
  return parts.join(' · ')
}

/**
 * 开缘按钮文案。
 *
 * @param p - 机缘包
 */
function claimLabel(p: HeritagePacket): string {
  if (p.already_claimed) return '已开缘'
  if (p.status === 'exhausted') return '已领完'
  return '开缘'
}

async function onClaim(p: HeritagePacket): Promise<void> {
  stickToBottom.value = true
  // 点击瞬间固定 id，避免列表刷新后误领其它包
  const packetId = Number(p.id)
  if (!packetId) {
    ElMessage.error('机缘无效')
    return
  }
  const err = await heritageStore.claim(packetId)
  if (err) {
    ElMessage.error(err)
    return
  }
  ElMessage.success(heritageStore.lastMessage || '开缘成功')
  void inventoryStore.load()
  void scrollBottom(true)
}

function onHeritageCreated(): void {
  stickToBottom.value = true
  void scrollBottom(true)
}
</script>

<template>
  <div class="chat-dock" :class="{ open: chatStore.dockOpen }">
    <button type="button" class="dock-toggle" @click="toggleDock">
      <span>聊天</span>
      <span
        v-if="chatStore.dmUnreadPeers > 0"
        class="badge"
        title="有未读私聊的对方人数"
      >{{ chatStore.dmUnreadPeers }}</span>
      <span
        v-if="chatStore.pendingInvites.length > 0"
        class="badge party-invite-badge"
        title="有队伍邀请，点击前往队伍页"
        @click.stop="router.push('/party')"
      >队</span>
      <span class="chev">{{ chatStore.dockOpen ? '▼' : '▲' }}</span>
    </button>

    <div v-show="chatStore.dockOpen" class="dock-panel">
      <div class="tabs">
        <button
          v-for="ch in sortedChannels"
          :key="`${ch.channel_type}-${ch.channel_ref ?? ch.label_zh}`"
          type="button"
          class="tab"
          :class="[
            `tab-${ch.channel_type}`,
            {
              active: ch.channel_ref && ch.channel_ref === chatStore.activeChannelRef,
              locked: !ch.can_access,
            },
          ]"
          :title="ch.lock_reason_zh || ch.label_zh"
          @click="onSelect(ch)"
        >
          {{ ch.label_zh }}
          <span v-if="tabBadge(ch)" class="badge sm">{{ tabBadge(ch) }}</span>
        </button>
      </div>

      <div
        v-if="chatStore.pendingInvites.length > 0"
        class="party-hint"
      >
        <span>有队伍邀请</span>
        <button type="button" class="party-link" @click="router.push('/party')">
          去队伍页
        </button>
      </div>

      <div ref="listEl" class="msg-list" @scroll="onListScroll">
        <el-empty
          v-if="chatStore.activeChannelRef && feedRows.length === 0 && !chatStore.loading"
          description="暂无消息"
          :image-size="40"
        />
        <template v-for="row in feedRows" :key="row.key">
          <div v-if="row.kind === 'chat'" class="msg">
            <span class="name" :style="nameStyle(row.message)">{{ row.message.sender_name }}</span>
            <span class="body">{{ row.message.body_zh }}</span>
          </div>
          <div
            v-else
            class="heritage-msg"
            :class="{
              highlight: heritageStore.highlightId === row.packet.id,
              finished: row.packet.status === 'exhausted',
            }"
          >
            <div class="heritage-msg-top">
              <span class="heritage-tag">机缘</span>
              <span class="heritage-sender">{{ row.packet.sender_name }}</span>
              <span class="heritage-mode">{{ row.packet.mode_label_zh }}</span>
            </div>
            <div class="heritage-summary">{{ heritageSummary(row.packet) }}</div>
            <div v-if="row.packet.note_zh" class="heritage-note">{{ row.packet.note_zh }}</div>
            <el-button
              size="small"
              type="success"
              :disabled="!row.packet.can_claim"
              :loading="heritageStore.loading"
              @click="onClaim(row.packet)"
            >
              {{ claimLabel(row.packet) }}
            </el-button>
          </div>
        </template>
      </div>

      <HeritageCard
        v-if="canSendHeritage && chatStore.activeChannelRef"
        :channel-ref="chatStore.activeChannelRef"
        :can-send="canSendHeritage"
        @created="onHeritageCreated"
      />

      <div class="composer">
        <el-input
          v-model="chatStore.draft"
          size="small"
          placeholder="输入消息…"
          :disabled="!chatStore.activeChannel?.can_send"
          @keyup.enter="onSend"
        />
        <el-button
          type="primary"
          size="small"
          :loading="chatStore.loading"
          :disabled="!chatStore.activeChannel?.can_send"
          @click="onSend"
        >
          发送
        </el-button>
      </div>
      <el-text v-if="chatStore.lastError" type="danger" size="small">
        {{ chatStore.lastError }}
      </el-text>
    </div>
  </div>
</template>

<style scoped>
.chat-dock {
  position: fixed;
  right: 1rem;
  bottom: 1rem;
  z-index: 40;
  width: min(400px, calc(100vw - 1.5rem));
  max-height: calc(100vh - 1.25rem);
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.35rem;
  pointer-events: none;
}

.dock-toggle,
.dock-panel {
  pointer-events: auto;
}

.dock-toggle {
  align-self: flex-end;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border: 1px solid #2f3540;
  background: #3a414d;
  color: #f2f4f7;
  border-radius: 999px;
  padding: 0.35rem 0.85rem;
  cursor: pointer;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.22);
  font-weight: 600;
  flex-shrink: 0;
}

.dock-toggle:hover {
  background: #2f3540;
  border-color: #1f2430;
}

.dock-toggle .badge {
  color: #ff8a80;
}

.dock-toggle .chev {
  color: #c5cbd6;
  opacity: 1;
}

.dock-panel {
  border: 1px solid var(--el-border-color);
  background: var(--el-bg-color);
  border-radius: 10px;
  padding: 0.55rem;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  /* 矮视口：整面板可上下滚，保证底部发机缘/发送可见 */
  max-height: min(560px, calc(100vh - 4.5rem));
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  flex-shrink: 0;
}

.tab {
  border: 1px solid #4a5568;
  background: #e8ecf1;
  color: #1a202c;
  border-radius: 6px;
  padding: 0.25rem 0.5rem;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
}

.tab-world {
  background: #d6e4f5;
  border-color: #2b6cb0;
  color: #1a365d;
}

.tab-sect {
  background: #d9f0e0;
  border-color: #276749;
  color: #1c4532;
}

.tab-dm {
  background: #ebe4f5;
  border-color: #553c9a;
  color: #322659;
}

.tab-mentor {
  background: #fde8d2;
  border-color: #c05621;
  color: #7b341e;
}

.tab-party {
  background: #fce7e7;
  border-color: #c53030;
  color: #742a2a;
}

.tab.active {
  color: #ffffff;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.12);
}

.tab-world.active {
  background: #2b6cb0;
  border-color: #1a365d;
}

.tab-sect.active {
  background: #276749;
  border-color: #1c4532;
}

.tab-dm.active {
  background: #553c9a;
  border-color: #322659;
}

.tab-mentor.active {
  background: #c05621;
  border-color: #7b341e;
}

.tab-party.active {
  background: #c53030;
  border-color: #742a2a;
}

.tab.locked {
  background: #d1d5db;
  border-color: #6b7280;
  color: #374151;
  cursor: not-allowed;
}

.tab.locked.active {
  background: #4b5563;
  border-color: #1f2937;
  color: #f9fafb;
}

.badge {
  color: #b91c1c;
  font-size: 0.75rem;
  font-weight: 700;
}

.badge.sm {
  margin-left: 0.15rem;
}

.party-hint {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
  font-size: 0.8rem;
  color: #742a2a;
}

.party-link {
  border: none;
  background: transparent;
  color: #c53030;
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
  font-size: inherit;
}

.party-invite-badge {
  cursor: pointer;
}

.msg-list {
  flex: 1 1 auto;
  /* 保证消息区不被机缘表单/多条红包挤没 */
  min-height: min(180px, 28vh);
  max-height: min(320px, 42vh);
  overflow-y: auto;
  overflow-x: hidden;
  border: 1px solid var(--el-border-color-extra-light);
  border-radius: 6px;
  padding: 0.45rem;
  scrollbar-gutter: stable;
}

.composer {
  display: flex;
  gap: 0.35rem;
  flex-shrink: 0;
  padding-bottom: 0.15rem;
}

.msg {
  display: flex;
  gap: 0.4rem;
  font-size: 0.8rem;
  margin-bottom: 0.35rem;
}

.msg .name {
  flex-shrink: 0;
  font-weight: 600;
}

.msg .body {
  color: #000000;
  word-break: break-word;
}

.heritage-msg {
  border: 1px solid #c05621;
  background: #fff7ed;
  border-radius: 8px;
  padding: 0.4rem 0.5rem;
  margin-bottom: 0.4rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  animation: slide-up 0.28s ease-out;
}

.heritage-msg.highlight {
  border-color: #276749;
  box-shadow: 0 0 0 1px rgba(39, 103, 73, 0.25);
}

.heritage-msg.finished {
  opacity: 0.8;
  border-style: dashed;
  background: #f3f4f6;
  border-color: #9ca3af;
}

.heritage-msg-top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.75rem;
}

.heritage-tag {
  background: #c05621;
  color: #fff;
  border-radius: 4px;
  padding: 0.05rem 0.35rem;
  font-weight: 700;
}

.heritage-sender {
  font-weight: 700;
  color: #7b341e;
}

.heritage-mode {
  color: #6b7280;
}

.heritage-summary {
  font-size: 0.78rem;
  color: #111827;
}

.heritage-note {
  font-size: 0.75rem;
  color: #4b5563;
}

.chev {
  font-size: 0.7rem;
  opacity: 0.7;
}

@keyframes slide-up {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
