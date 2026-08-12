<script setup lang="ts">
/**
 * 队伍面板：建队 / 队长邀请与踢人 / 离队 / 队友情报 / 待处理邀请。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useCharacterStore } from '../../stores/character'
import { useChatStore } from '../../stores/chat'
import { useFriendsStore } from '../../stores/friends'
import type { PartyMemberItem } from '../../types/chat'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const route = useRoute()
const router = useRouter()
const chatStore = useChatStore()
const friendsStore = useFriendsStore()
const characterStore = useCharacterStore()

const busy = ref(false)
const inviteName = ref('')
const expandedId = ref<number | null>(null)

const myId = computed(() => Number(characterStore.character?.id || 0))
const party = computed(() => chatStore.party)
const isLeader = computed(() => {
  const p = party.value
  if (!p || !myId.value) return false
  return Number(p.leader_character_id) === myId.value
})

onMounted(async () => {
  await friendsStore.refresh()
  const err = await chatStore.refreshPartyMe()
  if (err) emit('log', err, 'warning')
  const q = route.query.invite
  if (typeof q === 'string' && q.trim()) {
    inviteName.value = q.trim()
  }
})

watch(
  () => route.query.invite,
  (q) => {
    if (typeof q === 'string' && q.trim()) inviteName.value = q.trim()
  },
)

async function run(fn: () => Promise<string | null>, okHint: string): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await fn()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(okHint)
    emit('log', okHint, 'success')
  } finally {
    busy.value = false
  }
}

function onCreate(): Promise<void> {
  return run(() => chatStore.createParty(), '队伍已创建')
}

function onInvite(): Promise<void> {
  return run(() => chatStore.inviteToParty(inviteName.value), '邀请已发出')
}

function onLeave(): Promise<void> {
  return run(() => chatStore.leaveParty(), '已离队')
}

function onKick(m: PartyMemberItem): Promise<void> {
  return run(
    () =>
      chatStore.kickFromParty({
        peer_character_id: m.character_id,
        peer_name: m.name,
      }),
    `已将「${m.name}」移出队伍`,
  )
}

function onAccept(id: number): Promise<void> {
  return run(() => chatStore.acceptPartyInvite(id), '已加入队伍')
}

function onReject(id: number): Promise<void> {
  return run(() => chatStore.rejectPartyInvite(id), '已拒绝邀请')
}

function pickFriend(name: string): void {
  inviteName.value = name
}

function toggleExpand(id: number): void {
  expandedId.value = expandedId.value === id ? null : id
}

async function openPartyChat(): Promise<void> {
  const ref = party.value?.channel_ref
  if (!ref) {
    ElMessage.warning('暂无队伍频道')
    return
  }
  await chatStore.openDock()
  await chatStore.selectChannel(ref)
  emit('log', '已打开队伍聊天', 'info')
}

function techLine(m: PartyMemberItem): string {
  const list = m.technique_summary || []
  if (!list.length) return '无'
  return list
    .map((t) => `${t.name || t.id || '功法'}${t.level != null ? ` Lv${t.level}` : ''}`)
    .join('、')
}
</script>

<template>
  <el-card shadow="never" class="party-panel">
    <template #header>
      <div class="hdr">
        <el-text tag="b">队伍</el-text>
        <el-button size="small" @click="router.push('/friends')">道友</el-button>
      </div>
    </template>

    <el-divider content-position="left">待处理邀请</el-divider>
    <el-empty
      v-if="!chatStore.pendingInvites.length"
      description="暂无组队邀请"
      :image-size="40"
    />
    <div v-else class="list">
      <div
        v-for="inv in chatStore.pendingInvites"
        :key="inv.id"
        class="row"
      >
        <el-text>「{{ inv.inviter_name }}」邀请你入队</el-text>
        <div class="actions">
          <el-button size="small" type="primary" :loading="busy" @click="onAccept(inv.id)">
            接受
          </el-button>
          <el-button size="small" :loading="busy" @click="onReject(inv.id)">
            拒绝
          </el-button>
        </div>
      </div>
    </div>

    <template v-if="!party">
      <el-divider content-position="left">创建队伍</el-divider>
      <el-text size="small" type="info" class="hint">
        同一时间只能加入一支队伍；邀请与踢人仅队长可操作。
      </el-text>
      <el-button type="primary" size="small" :loading="busy" @click="onCreate">
        创建队伍
      </el-button>
    </template>

    <template v-else>
      <el-divider content-position="left">
        我的队伍 · #{{ party.id }}
        <el-tag v-if="isLeader" size="small" type="warning" class="leader-tag">队长</el-tag>
      </el-divider>

      <div class="toolbar">
        <el-button size="small" @click="openPartyChat">打开队伍聊天</el-button>
        <el-button size="small" type="danger" plain :loading="busy" @click="onLeave">
          离队
        </el-button>
      </div>

      <div v-if="isLeader" class="invite-box">
        <el-text size="small" type="info">队长邀请（须道友且对方在线）</el-text>
        <div v-if="friendsStore.friends.length" class="chips">
          <el-button
            v-for="f in friendsStore.friends"
            :key="f.friendship_id"
            size="small"
            @click="pickFriend(f.peer_name)"
          >
            {{ f.peer_name }}
          </el-button>
        </div>
        <div class="invite-row">
          <el-input
            v-model="inviteName"
            size="small"
            placeholder="队友道号"
            clearable
            @keyup.enter="onInvite"
          />
          <el-button type="primary" size="small" :loading="busy" @click="onInvite">
            邀请
          </el-button>
        </div>
      </div>

      <div class="list members">
        <div
          v-for="m in party.members"
          :key="m.character_id"
          class="member-card"
        >
          <div class="member-top" @click="toggleExpand(m.character_id)">
            <span class="online-dot" :class="{ on: m.online }" />
            <el-text tag="b">{{ m.name }}</el-text>
            <el-tag v-if="m.is_leader" size="small" type="warning">队长</el-tag>
            <el-tag size="small" type="info">
              {{ m.major_realm_name || m.major_realm || '—' }}
            </el-tag>
            <el-text size="small" type="info">{{ m.status_name || m.status || '' }}</el-text>
            <el-button
              v-if="isLeader && !m.is_leader"
              size="small"
              type="danger"
              plain
              :loading="busy"
              @click.stop="onKick(m)"
            >
              踢出
            </el-button>
          </div>
          <div v-if="expandedId === m.character_id" class="member-detail">
            <div>修为：{{ m.cultivation_points ?? 0 }}</div>
            <div>攻 / 血：{{ m.base_atk ?? 0 }} / {{ m.base_hp ?? 0 }}</div>
            <div>功法：{{ techLine(m) }}</div>
            <div>
              体质装备：
              {{
                m.constitution_equipped?.length
                  ? m.constitution_equipped.join('、')
                  : '无'
              }}
            </div>
            <div>状态：{{ m.online ? '在线' : '离线' }} · {{ m.status_name || '—' }}</div>
          </div>
        </div>
      </div>
    </template>
  </el-card>
</template>

<style scoped>
.hdr {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
}

.hint {
  display: block;
  margin-bottom: 0.5rem;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.row,
.member-top,
.invite-row,
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
}

.actions {
  display: flex;
  gap: 0.35rem;
}

.leader-tag {
  margin-left: 0.35rem;
}

.invite-box {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin: 0.5rem 0 0.75rem;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.member-card {
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  padding: 0.4rem 0;
}

.member-top {
  cursor: pointer;
}

.member-detail {
  margin: 0.35rem 0 0.25rem 1rem;
  font-size: 0.85rem;
  line-height: 1.5;
  color: var(--el-text-color-regular);
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
</style>
