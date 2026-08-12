<script setup lang="ts">
/**
 * 道友列表面板：修为/在线、私聊/赠礼/跳转队伍页/助战/面交。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { inviteAvatarAssist } from '../../api/avatar'
import { useChatStore } from '../../stores/chat'
import { useFriendsStore } from '../../stores/friends'
import { useMailStore } from '../../stores/mail'
import { useTradeStore } from '../../stores/trade'
import type { FriendItem } from '../../types/friends'

const props = withDefaults(
  defineProps<{
    /** 展示完整动作按钮（独立道友页为 true） */
    showActions?: boolean
  }>(),
  { showActions: true },
)

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const router = useRouter()
const friendsStore = useFriendsStore()
const chatStore = useChatStore()
const mailStore = useMailStore()
const tradeStore = useTradeStore()

const busy = ref(false)
const loadError = ref('')
const applyName = ref('')

/** 赠礼弹层 */
const giftVisible = ref(false)
const giftPeer = ref<FriendItem | null>(null)
const giftStones = ref(0)
const giftItemId = ref('')
const giftQty = ref(0)
const giftNote = ref('')

onMounted(async () => {
  loadError.value = ''
  const err = await friendsStore.refresh()
  if (err) {
    loadError.value = err
    emit('log', err, 'warning')
  }
})

async function onApply(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await friendsStore.applyByName(applyName.value)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(friendsStore.lastMessage || '已发送申请')
    emit('log', friendsStore.lastMessage || '道友申请已发送', 'success')
    applyName.value = ''
  } finally {
    busy.value = false
  }
}

async function onAccept(item: FriendItem): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await friendsStore.accept(item.friendship_id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(friendsStore.lastMessage || '已结为道友')
    emit('log', friendsStore.lastMessage || `与「${item.peer_name}」结交`, 'success')
  } finally {
    busy.value = false
  }
}

async function onReject(item: FriendItem): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await friendsStore.reject(item.friendship_id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(friendsStore.lastMessage || '已拒绝')
    emit('log', friendsStore.lastMessage || `已拒绝「${item.peer_name}」`, 'info')
  } finally {
    busy.value = false
  }
}

async function onRemove(item: FriendItem): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await friendsStore.remove(item.friendship_id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(friendsStore.lastMessage || '已解除')
    emit('log', friendsStore.lastMessage || `已与「${item.peer_name}」解除`, 'info')
  } finally {
    busy.value = false
  }
}

async function onDm(item: FriendItem): Promise<void> {
  const err = await chatStore.openDm(item.peer_character_id)
  if (err) {
    ElMessage.error(err)
    emit('log', err, 'warning')
    return
  }
  emit('log', `已打开与「${item.peer_name}」的私聊`, 'info')
}

function openGift(item: FriendItem): void {
  giftPeer.value = item
  giftStones.value = 0
  giftItemId.value = ''
  giftQty.value = 0
  giftNote.value = ''
  giftVisible.value = true
}

async function onGiftSubmit(): Promise<void> {
  if (!giftPeer.value || busy.value) return
  busy.value = true
  try {
    const items =
      giftQty.value > 0 && giftItemId.value.trim()
        ? [{ item_id: giftItemId.value.trim(), quantity: giftQty.value }]
        : []
    const err = await mailStore.giftToFriend({
      to_name: giftPeer.value.peer_name,
      spirit_stones: Number(giftStones.value) || 0,
      items,
      note_zh: giftNote.value || undefined,
    })
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(mailStore.lastMessage || '已投递邮箱')
    emit('log', mailStore.lastMessage || '赠礼已投递对方邮箱', 'success')
    giftVisible.value = false
  } finally {
    busy.value = false
  }
}

/**
 * 跳转独立队伍页，预填邀请道号（组队操作在队伍页完成）。
 *
 * @param item - 道友行
 */
function onParty(item: FriendItem): void {
  void router.push({ path: '/party', query: { invite: item.peer_name } })
  emit('log', `前往队伍页邀请「${item.peer_name}」`, 'info')
}

async function onAssist(item: FriendItem): Promise<void> {
  if (!item.assist_available) {
    ElMessage.warning('对方未开放化身助战或化身不可用')
    return
  }
  busy.value = true
  try {
    const envelope = await inviteAvatarAssist({
      target_character_id: item.peer_character_id,
    })
    if (envelope.code !== 0) {
      const msg = envelope.message || '助战邀请失败'
      ElMessage.error(msg)
      emit('log', msg, 'warning')
      return
    }
    ElMessage.success(envelope.data?.message || '助战邀请已发出')
    emit('log', envelope.data?.message || `已邀「${item.peer_name}」化身助战`, 'success')
    await friendsStore.refresh()
  } finally {
    busy.value = false
  }
}

async function onTrade(item: FriendItem): Promise<void> {
  if (!item.online) {
    ElMessage.warning('对方当前不在线')
    return
  }
  busy.value = true
  try {
    const err = await tradeStore.inviteFace({
      peer_character_id: item.peer_character_id,
      peer_name: item.peer_name,
    })
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(tradeStore.lastMessage || '面交邀请已发出')
    emit('log', tradeStore.lastMessage || `已向「${item.peer_name}」发起面交`, 'success')
    const sessionId = tradeStore.faceSession?.id
    await router.push({
      path: '/shop',
      query: {
        mode: 'auction',
        sub: 'face',
        peer: item.peer_name,
        ...(sessionId ? { session: String(sessionId) } : {}),
      },
    })
  } finally {
    busy.value = false
  }
}

function realmLabel(item: FriendItem): string {
  return item.peer_major_realm_name || item.peer_major_realm || '未知境界'
}
</script>

<template>
  <el-card shadow="never" class="friend-panel">
    <template #header>
      <div class="hdr">
        <el-text tag="b">道友</el-text>
        <el-text size="small" type="info">
          {{ friendsStore.friendCount }} / {{ friendsStore.maxFriends || '—' }}
        </el-text>
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

    <div class="apply-row">
      <el-input
        v-model="applyName"
        placeholder="对方道号"
        clearable
        size="small"
        style="max-width: 220px"
        @keyup.enter="onApply"
      />
      <el-button type="primary" size="small" :loading="busy" @click="onApply">
        申请道友
      </el-button>
    </div>

    <el-divider content-position="left">待我确认</el-divider>
    <el-empty
      v-if="!friendsStore.incoming.length"
      description="暂无待确认申请"
      :image-size="40"
    />
    <div v-else class="list">
      <div
        v-for="item in friendsStore.incoming"
        :key="item.friendship_id"
        class="row"
      >
        <el-text>{{ item.peer_name }}</el-text>
        <div class="actions">
          <el-button size="small" type="primary" :loading="busy" @click="onAccept(item)">
            接受
          </el-button>
          <el-button size="small" :loading="busy" @click="onReject(item)">
            拒绝
          </el-button>
        </div>
      </div>
    </div>

    <el-divider content-position="left">我的道友</el-divider>
    <el-empty
      v-if="!friendsStore.friends.length"
      description="尚无道友"
      :image-size="40"
    />
    <div v-else class="list">
      <div
        v-for="item in friendsStore.friends"
        :key="item.friendship_id"
        class="friend-card"
      >
        <div class="friend-meta">
          <span class="online-dot" :class="{ on: item.online }" :title="item.online ? '在线' : '离线'" />
          <el-text tag="b">{{ item.peer_name }}</el-text>
          <el-tag size="small" type="info">{{ realmLabel(item) }}</el-tag>
          <el-text size="small" type="info">
            修为 {{ item.peer_cultivation_points ?? 0 }}
          </el-text>
          <el-tag v-if="item.assist_available" size="small" type="success">可助战</el-tag>
        </div>
        <div v-if="props.showActions" class="actions wrap">
          <el-button size="small" :loading="busy" @click="onDm(item)">私聊</el-button>
          <el-button size="small" :loading="busy" @click="openGift(item)">赠礼</el-button>
          <el-button
            size="small"
            :disabled="!item.online"
            :loading="busy"
            @click="onParty(item)"
          >
            组队
          </el-button>
          <el-button
            size="small"
            :disabled="!item.assist_available"
            :loading="busy"
            @click="onAssist(item)"
          >
            助战
          </el-button>
          <el-button
            size="small"
            :disabled="!item.online"
            :loading="busy"
            @click="onTrade(item)"
          >
            交易
          </el-button>
          <el-button size="small" type="danger" plain :loading="busy" @click="onRemove(item)">
            解除
          </el-button>
        </div>
      </div>
    </div>

    <el-divider content-position="left">已发出申请</el-divider>
    <el-empty
      v-if="!friendsStore.outgoing.length"
      description="无待对方确认的申请"
      :image-size="40"
    />
    <div v-else class="list">
      <div
        v-for="item in friendsStore.outgoing"
        :key="item.friendship_id"
        class="row"
      >
        <el-text>{{ item.peer_name }}</el-text>
        <el-tag size="small" type="info">等待确认</el-tag>
      </div>
    </div>

    <el-dialog
      v-model="giftVisible"
      title="赠礼 / 留言（物品经邮箱领取）"
      width="420px"
      destroy-on-close
    >
      <el-text v-if="giftPeer" size="small" type="info">
        送给「{{ giftPeer.peer_name }}」· 纯留言可只填附言；附物走赠送入邮箱。
      </el-text>
      <div class="gift-form">
        <el-input-number
          v-model="giftStones"
          :min="0"
          :step="10"
          size="small"
          controls-position="right"
        />
        <el-text size="small">灵石</el-text>
        <el-input v-model="giftItemId" placeholder="物品 id（可选）" size="small" />
        <el-input-number
          v-model="giftQty"
          :min="0"
          :step="1"
          size="small"
          controls-position="right"
        />
        <el-input
          v-model="giftNote"
          type="textarea"
          :rows="2"
          placeholder="附言 / 留言"
          size="small"
        />
      </div>
      <template #footer>
        <el-button size="small" @click="giftVisible = false">取消</el-button>
        <el-button type="primary" size="small" :loading="busy" @click="onGiftSubmit">
          送出
        </el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<style scoped>
.hdr {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
}

.hint {
  margin-bottom: 0.5rem;
}

.apply-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 0.5rem;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.row,
.friend-card {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.friend-card {
  padding: 0.45rem 0.35rem;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.friend-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
}

.online-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c0c4cc;
  flex-shrink: 0;
}

.online-dot.on {
  background: #67c23a;
}

.actions {
  display: flex;
  gap: 0.35rem;
}

.actions.wrap {
  flex-wrap: wrap;
}

.gift-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
</style>
