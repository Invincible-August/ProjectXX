<script setup lang="ts">
/**
 * 赠送面板：对道友送灵石/物品 → 对方邮箱领取。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useFriendsStore } from '../../stores/friends'
import { useMailStore } from '../../stores/mail'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const mailStore = useMailStore()
const friendsStore = useFriendsStore()
const busy = ref(false)

const toName = ref('')
const spiritStones = ref(0)
const itemId = ref('herb_spirit_grass')
const itemQty = ref(0)
const noteZh = ref('')

onMounted(async () => {
  const err = await friendsStore.refresh()
  if (err) emit('log', err, 'warning')
})

function pickFriend(name: string): void {
  toName.value = name
}

async function onGift(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const items =
      itemQty.value > 0 && itemId.value.trim()
        ? [{ item_id: itemId.value.trim(), quantity: itemQty.value }]
        : []
    const err = await mailStore.giftToFriend({
      to_name: toName.value,
      spirit_stones: Number(spiritStones.value) || 0,
      items,
      note_zh: noteZh.value || undefined,
    })
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(mailStore.lastMessage || '已赠送')
    emit('log', mailStore.lastMessage || '赠送已投递邮箱', 'success')
    spiritStones.value = 0
    itemQty.value = 0
    noteZh.value = ''
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never" class="gift-panel">
    <template #header>
      <el-text tag="b">赠送道友</el-text>
    </template>

    <el-text size="small" type="info" class="hint">
      仅可赠送给已结交道友；物品须可交易且非绑定；对方在邮箱领取。
    </el-text>

    <div v-if="friendsStore.friends.length" class="friend-chips">
      <el-button
        v-for="f in friendsStore.friends"
        :key="f.friendship_id"
        size="small"
        @click="pickFriend(f.peer_name)"
      >
        {{ f.peer_name }}
      </el-button>
    </div>

    <div class="form">
      <el-input v-model="toName" placeholder="对方道号" size="small" clearable />
      <el-input-number
        v-model="spiritStones"
        :min="0"
        :step="10"
        size="small"
        controls-position="right"
      />
      <el-text size="small" type="info">灵石</el-text>
      <el-input v-model="itemId" placeholder="物品 id" size="small" />
      <el-input-number
        v-model="itemQty"
        :min="0"
        :step="1"
        size="small"
        controls-position="right"
      />
      <el-text size="small" type="info">数量（0=不送物）</el-text>
      <el-input
        v-model="noteZh"
        type="textarea"
        :rows="2"
        placeholder="附言（可选）"
        size="small"
      />
      <el-button type="primary" size="small" :loading="busy" @click="onGift">
        送出
      </el-button>
    </div>
  </el-card>
</template>

<style scoped>
.hint {
  display: block;
  margin-bottom: 0.75rem;
}
.friend-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.75rem;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  max-width: 360px;
}
</style>
