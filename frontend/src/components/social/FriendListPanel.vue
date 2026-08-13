<script setup lang="ts">
/**
 * 道友关系单页：申请栏 + 待确认 + 我的道友/道侣/炉鼎/主人。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { inviteAvatarAssist } from '../../api/avatar'
import { useBondsStore } from '../../stores/bonds'
import { useChatStore } from '../../stores/chat'
import { useFriendsStore } from '../../stores/friends'
import { useTradeStore } from '../../stores/trade'
import type { BondItem } from '../../types/bonds'
import type { FriendItem, FriendProfileCard } from '../../types/friends'

const props = withDefaults(
  defineProps<{
    showActions?: boolean
  }>(),
  { showActions: true },
)

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const OFFLINE_TIP = '道友不在本界'

const router = useRouter()
const friendsStore = useFriendsStore()
const bondsStore = useBondsStore()
const chatStore = useChatStore()
const tradeStore = useTradeStore()

const busy = ref(false)
const loadError = ref('')
const applyName = ref('')
const privacyBusy = ref(false)

const profileVisible = ref(false)
const profileLoading = ref(false)
const profileCard = ref<FriendProfileCard | null>(null)
const profileTitle = ref('')

onMounted(async () => {
  loadError.value = ''
  const [err, bondErr, privErr] = await Promise.all([
    friendsStore.refresh(),
    bondsStore.refresh(),
    friendsStore.loadPrivacy(),
  ])
  if (err) {
    loadError.value = err
    emit('log', err, 'warning')
  }
  if (bondErr) emit('log', bondErr, 'warning')
  if (privErr) emit('log', privErr, 'warning')
})

function requireOnline(item: FriendItem): boolean {
  if (item.online) return true
  ElMessage.warning(OFFLINE_TIP)
  emit('log', `「${item.peer_name}」${OFFLINE_TIP}`, 'warning')
  return false
}

function isCompanion(peerId: number): boolean {
  return bondsStore.companions.some((c) => Number(c.peer_character_id) === Number(peerId))
}

function isFriend(peerId: number): boolean {
  return friendsStore.friends.some((f) => Number(f.peer_character_id) === Number(peerId))
}

async function onApplyFriend(): Promise<void> {
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

async function onApplyCompanion(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await bondsStore.applyByName(applyName.value)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(bondsStore.lastMessage || '已发送道侣申请')
    emit('log', bondsStore.lastMessage || '道侣申请已发送', 'success')
    applyName.value = ''
  } finally {
    busy.value = false
  }
}

async function onFriendToCompanion(item: FriendItem): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await bondsStore.applyByCharacterId(item.peer_character_id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(bondsStore.lastMessage || '已申请道侣')
    emit('log', bondsStore.lastMessage || `已向「${item.peer_name}」申请道侣`, 'success')
  } finally {
    busy.value = false
  }
}

async function onCompanionToFriend(item: BondItem): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await friendsStore.applyByCharacterId(item.peer_character_id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(friendsStore.lastMessage || '已申请道友')
    emit('log', friendsStore.lastMessage || `已向「${item.peer_name}」申请道友`, 'success')
  } finally {
    busy.value = false
  }
}

async function onAcceptCompanion(item: BondItem): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await bondsStore.accept(item.bond_id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(bondsStore.lastMessage || '已结为道侣')
    emit('log', bondsStore.lastMessage || `与「${item.peer_name}」结为道侣`, 'success')
  } finally {
    busy.value = false
  }
}

async function onRejectCompanion(item: BondItem): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await bondsStore.reject(item.bond_id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(bondsStore.lastMessage || '已拒绝')
    emit('log', bondsStore.lastMessage || '已拒绝道侣申请', 'info')
  } finally {
    busy.value = false
  }
}

async function onRemoveBond(item: BondItem): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await bondsStore.remove(item.bond_id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(bondsStore.lastMessage || '已解除')
    emit('log', bondsStore.lastMessage || `已解除与「${item.peer_name}」`, 'info')
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
  if (!requireOnline(item)) return
  const err = await chatStore.openDm(item.peer_character_id)
  if (err) {
    ElMessage.error(err)
    emit('log', err, 'warning')
    return
  }
  emit('log', `已打开与「${item.peer_name}」的私聊`, 'info')
}

function onParty(item: FriendItem): void {
  if (!requireOnline(item)) return
  void router.push({ path: '/party', query: { invite: item.peer_name } })
  emit('log', `前往队伍页邀请「${item.peer_name}」`, 'info')
}

async function onAssist(item: FriendItem): Promise<void> {
  busy.value = true
  try {
    const envelope = await inviteAvatarAssist({
      target_character_id: item.peer_character_id,
    })
    if (envelope.code !== 0) {
      const msg = envelope.message || '邀请化身失败'
      ElMessage.error(msg)
      emit('log', msg, 'warning')
      return
    }
    ElMessage.success(envelope.data?.message || '化身已加入助战')
    emit('log', envelope.data?.message || `已邀请「${item.peer_name}」化身助战`, 'success')
    await friendsStore.refresh()
  } finally {
    busy.value = false
  }
}

async function onTrade(item: FriendItem): Promise<void> {
  if (!requireOnline(item)) return
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
    ElMessage.success(tradeStore.lastMessage || '交易邀请已发出')
    emit('log', tradeStore.lastMessage || `已向「${item.peer_name}」发起交易`, 'success')
    const sessionId = tradeStore.faceSession?.id
    await router.push({
      path: '/social',
      query: {
        mode: 'trade',
        peer: item.peer_name,
        ...(sessionId ? { session: String(sessionId) } : {}),
      },
    })
  } finally {
    busy.value = false
  }
}

async function onViewProfile(item: FriendItem): Promise<void> {
  profileTitle.value = item.peer_name
  profileCard.value = null
  profileVisible.value = true
  profileLoading.value = true
  try {
    const { err, profile } = await friendsStore.loadProfile(item.peer_character_id)
    if (err) {
      ElMessage.warning(err)
      emit('log', err, 'warning')
      profileVisible.value = false
      return
    }
    profileCard.value = profile
  } finally {
    profileLoading.value = false
  }
}

async function onTogglePrivacy(val: string | number | boolean): Promise<void> {
  privacyBusy.value = true
  try {
    const err = await friendsStore.setPrivacy(Boolean(val))
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(friendsStore.lastMessage || '已更新')
    emit('log', friendsStore.lastMessage || '隐私设置已更新', 'success')
  } finally {
    privacyBusy.value = false
  }
}

function realmLabel(item: FriendItem): string {
  return item.peer_major_realm_name || item.peer_major_realm || '未知境界'
}

/** 炉鼎到期本地时间展示 */
function formatExpire(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleString()
}

function sourceLabel(card: FriendProfileCard): string {
  if (card.source === 'live') return '实时'
  if (card.source === 'snapshot') return '离线快照'
  return String(card.source || '')
}

function techName(row: Record<string, unknown>): string {
  return String(row.name_zh || row.name || row.technique_id || '功法')
}

function techLevel(row: Record<string, unknown>): string {
  const lv = row.level ?? row.rank ?? row.grade
  return lv != null ? `Lv.${lv}` : ''
}
</script>

<template>
  <el-card shadow="never" class="friend-panel">
    <template #header>
      <div class="hdr">
        <el-text tag="b">道友关系</el-text>
        <el-text size="small" type="info">
          道友 {{ friendsStore.friendCount }}/{{ friendsStore.maxFriends || '—' }} · 道侣
          {{ bondsStore.companionCount }}/{{ bondsStore.maxCompanions || '—' }}
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

    <div class="privacy-row">
      <el-text size="small">允许道友查看我的修为 / 功法 / 属性</el-text>
      <el-switch
        :model-value="friendsStore.profileVisible"
        :loading="privacyBusy"
        @change="onTogglePrivacy"
      />
    </div>
    <el-text size="small" type="info" class="privacy-hint">
      关闭后，道友查看将提示「道友已遮掩天机」。
    </el-text>

    <div class="apply-row">
      <el-input
        v-model="applyName"
        placeholder="对方道号"
        clearable
        size="small"
        style="max-width: 220px"
        @keyup.enter="onApplyFriend"
      />
      <el-button type="primary" size="small" :loading="busy" @click="onApplyFriend">
        申请道友
      </el-button>
      <el-button type="success" size="small" :loading="busy" @click="onApplyCompanion">
        申请道侣
      </el-button>
    </div>

    <el-divider content-position="left">待我确认 · 道友</el-divider>
    <el-empty
      v-if="!friendsStore.incoming.length"
      description="暂无待确认道友申请"
      :image-size="36"
    />
    <div v-else class="list">
      <div
        v-for="item in friendsStore.incoming"
        :key="'fi-' + item.friendship_id"
        class="row"
      >
        <el-text>{{ item.peer_name }}</el-text>
        <div class="actions">
          <el-button size="small" type="primary" :loading="busy" @click="onAccept(item)">
            接受
          </el-button>
          <el-button size="small" :loading="busy" @click="onReject(item)">拒绝</el-button>
        </div>
      </div>
    </div>

    <el-divider content-position="left">待我确认 · 道侣</el-divider>
    <el-empty
      v-if="!bondsStore.companionIncoming.length"
      description="暂无待确认道侣申请"
      :image-size="36"
    />
    <div v-else class="list">
      <div
        v-for="item in bondsStore.companionIncoming"
        :key="'ci-' + item.bond_id"
        class="row"
      >
        <el-text>{{ item.peer_name }}</el-text>
        <div class="actions">
          <el-button
            size="small"
            type="primary"
            :loading="busy"
            @click="onAcceptCompanion(item)"
          >
            接受
          </el-button>
          <el-button size="small" :loading="busy" @click="onRejectCompanion(item)">
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
        :key="'f-' + item.friendship_id"
        class="friend-card"
      >
        <div class="friend-meta">
          <span
            class="presence-dot"
            :class="{ on: item.online }"
            :title="item.online ? '在线' : '离线'"
          />
          <el-tag size="small" :type="item.online ? 'success' : 'info'">
            {{ item.online ? '在线' : '离线' }}
          </el-tag>
          <button type="button" class="name-btn" @click="onViewProfile(item)">
            <el-text tag="b">{{ item.peer_name }}</el-text>
          </button>
          <el-tag size="small" type="info">{{ realmLabel(item) }}</el-tag>
          <el-text size="small" type="info">
            修为 {{ item.peer_cultivation_points ?? 0 }}
          </el-text>
          <el-tag v-if="item.assist_available" size="small" type="success">可邀化身</el-tag>
        </div>
        <div v-if="props.showActions" class="actions wrap">
          <el-button size="small" :loading="busy" @click="onViewProfile(item)">查看</el-button>
          <el-button size="small" :loading="busy" @click="onDm(item)">私聊</el-button>
          <el-button size="small" :loading="busy" @click="onParty(item)">组队</el-button>
          <el-button size="small" :loading="busy" @click="onAssist(item)">邀请化身</el-button>
          <el-button size="small" :loading="busy" @click="onTrade(item)">交易</el-button>
          <el-button
            v-if="!isCompanion(item.peer_character_id)"
            size="small"
            type="success"
            plain
            :loading="busy"
            @click="onFriendToCompanion(item)"
          >
            申请道侣
          </el-button>
          <el-button size="small" type="danger" plain :loading="busy" @click="onRemove(item)">
            解除
          </el-button>
        </div>
      </div>
    </div>

    <el-divider content-position="left">我的道侣</el-divider>
    <el-empty
      v-if="!bondsStore.companions.length"
      description="尚无道侣"
      :image-size="40"
    />
    <div v-else class="list">
      <div v-for="item in bondsStore.companions" :key="'c-' + item.bond_id" class="friend-card">
        <div class="friend-meta">
          <span
            class="presence-dot"
            :class="{ on: item.online }"
            :title="item.online ? '在线' : '离线'"
          />
          <el-tag size="small" :type="item.online ? 'success' : 'info'">
            {{ item.online ? '在线' : '离线' }}
          </el-tag>
          <el-text tag="b">{{ item.peer_name }}</el-text>
          <el-tag size="small" type="info">
            {{ item.peer_major_realm_name || item.peer_major_realm || '—' }}
          </el-tag>
        </div>
        <div v-if="props.showActions" class="actions wrap">
          <el-button
            v-if="!isFriend(item.peer_character_id)"
            size="small"
            type="primary"
            plain
            :loading="busy"
            @click="onCompanionToFriend(item)"
          >
            申请道友
          </el-button>
          <el-button
            size="small"
            type="danger"
            plain
            :loading="busy"
            @click="onRemoveBond(item)"
          >
            解除
          </el-button>
        </div>
      </div>
    </div>

    <el-divider content-position="left">我的炉鼎</el-divider>
    <el-text size="small" type="info" class="privacy-hint">
      {{ bondsStore.vesselHintZh }}
    </el-text>
    <el-empty
      v-if="!bondsStore.vessels.length"
      description="尚无炉鼎"
      :image-size="40"
    />
    <div v-else class="list">
      <div v-for="item in bondsStore.vessels" :key="'v-' + item.bond_id" class="friend-card">
        <div class="friend-meta">
          <span
            class="presence-dot"
            :class="{ on: item.online }"
            :title="item.online ? '在线' : '离线'"
          />
          <el-tag size="small" :type="item.online ? 'success' : 'info'">
            {{ item.online ? '在线' : '离线' }}
          </el-tag>
          <el-text tag="b">{{ item.peer_name }}</el-text>
          <el-text v-if="item.expires_at" size="small" type="info">
            · 至 {{ formatExpire(item.expires_at) }}
          </el-text>
        </div>
        <div class="actions wrap">
          <el-button
            size="small"
            type="danger"
            plain
            :loading="busy"
            @click="onRemoveBond(item)"
          >
            解除炉鼎
          </el-button>
        </div>
      </div>
    </div>

    <template v-if="bondsStore.myMaster">
      <el-divider content-position="left">我的主人</el-divider>
      <div class="list">
        <div class="friend-card">
          <div class="friend-meta">
            <span
              class="presence-dot"
              :class="{ on: bondsStore.myMaster.online }"
              :title="bondsStore.myMaster.online ? '在线' : '离线'"
            />
            <el-tag
              size="small"
              :type="bondsStore.myMaster.online ? 'success' : 'info'"
            >
              {{ bondsStore.myMaster.online ? '在线' : '离线' }}
            </el-tag>
            <el-text tag="b">{{ bondsStore.myMaster.peer_name }}</el-text>
            <el-tag size="small" type="warning">主人</el-tag>
            <el-text
              v-if="bondsStore.myMaster.expires_at"
              size="small"
              type="info"
            >
              · 至 {{ formatExpire(bondsStore.myMaster.expires_at) }}
            </el-text>
          </div>
        </div>
      </div>
    </template>

    <el-divider content-position="left">已发出申请</el-divider>
    <el-empty
      v-if="!friendsStore.outgoing.length && !bondsStore.companionOutgoing.length"
      description="无待对方确认的申请"
      :image-size="36"
    />
    <div v-else class="list">
      <div
        v-for="item in friendsStore.outgoing"
        :key="'fo-' + item.friendship_id"
        class="row"
      >
        <el-text>{{ item.peer_name }}</el-text>
        <el-tag size="small" type="info">道友 · 等待确认</el-tag>
      </div>
      <div
        v-for="item in bondsStore.companionOutgoing"
        :key="'co-' + item.bond_id"
        class="row"
      >
        <el-text>{{ item.peer_name }}</el-text>
        <el-tag size="small" type="success">道侣 · 等待确认</el-tag>
      </div>
    </div>

    <el-dialog
      v-model="profileVisible"
      :title="`道友 · ${profileTitle}`"
      width="480px"
      destroy-on-close
      append-to-body
    >
      <div v-loading="profileLoading">
        <template v-if="profileCard">
          <div class="prof-row">
            <el-tag size="small" :type="profileCard.online ? 'success' : 'info'">
              {{ profileCard.online ? '在线' : '离线' }}
            </el-tag>
            <el-tag size="small" type="warning">{{ sourceLabel(profileCard) }}</el-tag>
            <el-text v-if="profileCard.snapshot_at" size="small" type="info">
              快照 {{ profileCard.snapshot_at }}
            </el-text>
          </div>
          <p class="prof-line">
            <el-text tag="b">{{ profileCard.name }}</el-text>
            · {{ profileCard.major_realm_name || profileCard.major_realm }}
            · 第 {{ profileCard.realm_stage }} 层
          </p>
          <p class="prof-line">
            境界进度 {{ profileCard.realm_progress }}
            <template v-if="profileCard.cultivation_required">
              / {{ profileCard.cultivation_required }}
            </template>
            · 修灵池 {{ profileCard.cultivation_points }}
          </p>
          <el-divider content-position="left">属性</el-divider>
          <div class="attr-grid">
            <span>物攻 {{ profileCard.combat_final.phys_atk }}</span>
            <span>法攻 {{ profileCard.combat_final.magic_atk }}</span>
            <span>气血 {{ profileCard.combat_final.hp }}</span>
            <span>物防 {{ profileCard.combat_final.phys_def }}</span>
            <span>法防 {{ profileCard.combat_final.magic_def }}</span>
            <span>速度 {{ profileCard.combat_final.speed }}</span>
          </div>
          <el-divider content-position="left">功法</el-divider>
          <el-empty
            v-if="!profileCard.technique_summary?.length"
            description="暂无功法摘要"
            :image-size="36"
          />
          <ul v-else class="tech-list">
            <li v-for="(t, i) in profileCard.technique_summary" :key="i">
              {{ techName(t) }} {{ techLevel(t) }}
            </li>
          </ul>
        </template>
      </div>
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

.privacy-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}

.privacy-hint {
  display: block;
  margin-bottom: 0.75rem;
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

.name-btn {
  border: none;
  background: transparent;
  padding: 0;
  cursor: pointer;
}

.name-btn:hover :deep(.el-text) {
  color: var(--el-color-primary);
  text-decoration: underline;
}

.presence-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c0c4cc;
  flex-shrink: 0;
}

.presence-dot.on {
  background: #67c23a;
}

.actions {
  display: flex;
  gap: 0.35rem;
}

.actions.wrap {
  flex-wrap: wrap;
}

.prof-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: center;
  margin-bottom: 0.5rem;
}

.prof-line {
  margin: 0.25rem 0;
  font-size: 0.9rem;
}

.attr-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.35rem;
  font-size: 0.85rem;
}

.tech-list {
  margin: 0;
  padding-left: 1.1rem;
  font-size: 0.85rem;
}
</style>
