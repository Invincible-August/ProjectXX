<script setup lang="ts">
/**
 * 独立私聊弹窗：左会话列表、右对话；服务端持久最近 N 条。
 */
import { nextTick, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useChatStore } from '../../stores/chat'
import type { ChatChannelItem, ChatMessageItem } from '../../types/chat'
import { chatNameColorByMajorRealm } from '../../utils/chatRealmNameColor'

const chatStore = useChatStore()
const listEl = ref<HTMLElement | null>(null)
const stickToBottom = ref(true)

watch(
  () => chatStore.dmMessages.length,
  () => {
    void scrollBottom()
  },
)

watch(
  () => chatStore.dmChannelRef,
  () => {
    stickToBottom.value = true
    void scrollBottom(true)
  },
)

async function scrollBottom(force = false): Promise<void> {
  await nextTick()
  if (!listEl.value) return
  if (!force && !stickToBottom.value) return
  listEl.value.scrollTop = listEl.value.scrollHeight
}

function onListScroll(): void {
  const el = listEl.value
  if (!el) return
  const gap = el.scrollHeight - el.scrollTop - el.clientHeight
  stickToBottom.value = gap < 48
}

function nameStyle(m: ChatMessageItem): { color: string } {
  return { color: chatNameColorByMajorRealm(m.sender_major_realm) }
}

async function onPick(ch: ChatChannelItem): Promise<void> {
  if (!ch.channel_ref) return
  stickToBottom.value = true
  const err = await chatStore.selectDm(ch.channel_ref)
  if (err) ElMessage.error(err)
  void scrollBottom(true)
}

async function onSend(): Promise<void> {
  stickToBottom.value = true
  const err = await chatStore.sendDm()
  if (err) ElMessage.error(err)
  else void scrollBottom(true)
}

async function onClear(): Promise<void> {
  if (!chatStore.dmChannelRef) return
  try {
    await ElMessageBox.confirm(
      '将清空与此人的全部私聊记录（双方均不可再看），是否继续？',
      '清空私聊',
      { type: 'warning', confirmButtonText: '清空', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const err = await chatStore.clearDm()
  if (err) ElMessage.error(err)
  else ElMessage.success('已清空私聊记录')
}

function peerLabel(ch: ChatChannelItem): string {
  return ch.peer_name || ch.label_zh || ch.channel_ref || '私聊'
}
</script>

<template>
  <el-dialog
    :model-value="chatStore.dmDialogOpen"
    title="私聊"
    width="720px"
    class="dm-dialog"
    destroy-on-close
    @close="chatStore.closeDmDialog()"
  >
    <div class="dm-body">
      <aside class="dm-peers">
        <el-empty
          v-if="!chatStore.dmChannels.length"
          description="暂无私聊会话"
          :image-size="48"
        />
        <button
          v-for="ch in chatStore.dmChannels"
          :key="ch.channel_ref || ch.label_zh"
          type="button"
          class="peer-row"
          :class="{ active: ch.channel_ref === chatStore.dmChannelRef }"
          @click="onPick(ch)"
        >
          <span class="peer-name">{{ peerLabel(ch) }}</span>
          <span v-if="Number(ch.unread) > 0" class="peer-badge">{{ ch.unread }}</span>
        </button>
      </aside>

      <section class="dm-thread">
        <div class="thread-toolbar">
          <el-text tag="b">
            {{ chatStore.dmActiveChannel ? peerLabel(chatStore.dmActiveChannel) : '选择会话' }}
          </el-text>
          <el-button
            size="small"
            type="danger"
            plain
            :disabled="!chatStore.dmChannelRef"
            :loading="chatStore.loading"
            @click="onClear"
          >
            清空聊天
          </el-button>
        </div>

        <div ref="listEl" class="msg-list" @scroll="onListScroll">
          <el-empty
            v-if="chatStore.dmChannelRef && !chatStore.dmMessages.length && !chatStore.loading"
            description="暂无消息"
            :image-size="40"
          />
          <div v-for="m in chatStore.dmMessages" :key="m.id" class="msg">
            <span class="name" :style="nameStyle(m)">{{ m.sender_name }}</span>
            <span class="body">{{ m.body_zh }}</span>
          </div>
        </div>

        <div class="composer">
          <el-input
            v-model="chatStore.dmDraft"
            size="small"
            placeholder="输入私聊内容"
            :disabled="!chatStore.dmChannelRef"
            maxlength="200"
            @keyup.enter="onSend"
          />
          <el-button
            type="primary"
            size="small"
            :loading="chatStore.loading"
            :disabled="!chatStore.dmChannelRef"
            @click="onSend"
          >
            发送
          </el-button>
        </div>
        <el-text size="small" type="info" class="hint">
          私聊记录会保存；每个会话最多保留最近
          {{ chatStore.dmHistoryLimit }} 条（管理后台可配）。
        </el-text>
      </section>
    </div>
  </el-dialog>
</template>

<style scoped>
.dm-body {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  gap: 0.75rem;
  min-height: 360px;
}

@media (max-width: 640px) {
  .dm-body {
    grid-template-columns: 1fr;
  }
}

.dm-peers {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  border-right: 1px solid var(--el-border-color-lighter);
  padding-right: 0.5rem;
  max-height: 420px;
  overflow-y: auto;
}

.peer-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.35rem;
  border: 1px solid transparent;
  background: transparent;
  border-radius: 6px;
  padding: 0.4rem 0.5rem;
  cursor: pointer;
  text-align: left;
}

.peer-row:hover {
  background: rgba(0, 0, 0, 0.04);
}

.peer-row.active {
  border-color: #2b6cb0;
  background: #e8f1fb;
}

.peer-name {
  font-size: 0.85rem;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.peer-badge {
  color: #b91c1c;
  font-size: 0.75rem;
  font-weight: 700;
}

.dm-thread {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  min-width: 0;
}

.thread-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.msg-list {
  flex: 1 1 auto;
  min-height: 220px;
  max-height: 320px;
  overflow-y: auto;
  border: 1px solid var(--el-border-color-extra-light);
  border-radius: 6px;
  padding: 0.45rem;
}

.msg {
  display: flex;
  gap: 0.4rem;
  font-size: 0.85rem;
  margin-bottom: 0.35rem;
}

.msg .name {
  flex-shrink: 0;
  font-weight: 600;
}

.msg .body {
  color: #000;
  word-break: break-word;
}

.composer {
  display: flex;
  gap: 0.35rem;
}

.hint {
  display: block;
}
</style>
