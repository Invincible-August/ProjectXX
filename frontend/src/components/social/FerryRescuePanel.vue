<script setup lang="ts">
/**
 * 社交页引渡救援：道友/同门救待引渡角色（救援者支付较低灵石）。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useFriendsStore } from '../../stores/friends'
import { useFerryStore } from '../../stores/ferry'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const friendsStore = useFriendsStore()
const ferryStore = useFerryStore()
const busy = ref(false)
const targetName = ref('')
const mode = ref<'friend' | 'sect'>('friend')

const costHint = computed(() => {
  const sr = ferryStore.socialRescueCosts
  if (!sr) return '道友引渡低于自救；救援者支付灵石。'
  return (
    `道友引渡 ${sr.friend_cost} 灵石 / 同门 ${sr.sect_cost} / 自救 ${sr.self_rescue_cost}` +
    `（道友省 ${sr.friend_cheaper_by ?? 0}）`
  )
})

onMounted(async () => {
  await friendsStore.refresh()
  const err = await ferryStore.loadFerry()
  if (err) emit('log', err, 'warning')
})

function pickFriend(name: string): void {
  targetName.value = name
  mode.value = 'friend'
}

async function onRescue(): Promise<void> {
  if (busy.value) return
  const name = targetName.value.trim()
  if (!name) {
    ElMessage.warning('请填写待救道号')
    return
  }
  busy.value = true
  try {
    const err = await ferryStore.doSocialRescue(mode.value, name)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(ferryStore.lastMessage || '引渡成功')
    emit('log', ferryStore.lastMessage || '引渡成功', 'success')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">引渡救援</el-text>
    </template>
    <el-text size="small" type="info" class="hint">
      对方须处于待引渡；你支付灵石（低于对方自救）。同图判定当前为联调桩。
    </el-text>
    <el-text size="small" class="hint">{{ costHint }}</el-text>

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

    <div class="form">
      <el-radio-group v-model="mode" size="small">
        <el-radio-button value="friend">道友引渡</el-radio-button>
        <el-radio-button value="sect">同门引渡</el-radio-button>
      </el-radio-group>
      <el-input v-model="targetName" size="small" placeholder="待救道号" clearable />
      <el-button type="primary" size="small" :loading="busy" @click="onRescue">
        发起引渡
      </el-button>
    </div>
  </el-card>
</template>

<style scoped>
.hint {
  display: block;
  margin-bottom: 0.5rem;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.6rem;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  max-width: 360px;
}
</style>
