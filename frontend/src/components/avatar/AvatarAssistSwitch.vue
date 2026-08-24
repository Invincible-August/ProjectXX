<script setup lang="ts">
/**
 * 化身助战开关：放在化身简览原名称位置。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { setAvatarAssistSettings } from '../../api/avatar'
import { useAvatarStore } from '../../stores/avatar'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const avatarStore = useAvatarStore()
const busy = ref(false)
const enabled = ref(Boolean(avatarStore.avatar?.assist_friends_enabled))

watch(
  () => avatarStore.avatar?.assist_friends_enabled,
  (v) => {
    enabled.value = Boolean(v)
  },
)

const unlocked = computed(
  () =>
    (avatarStore.avatar?.features ?? avatarStore.features?.features ?? []).find(
      (f) => f.feature_id === 'friend_assist',
    )?.unlocked ?? false,
)

const lockHint = computed(() => {
  const feat = (avatarStore.avatar?.features ?? avatarStore.features?.features ?? []).find(
    (f) => f.feature_id === 'friend_assist',
  )
  if (feat && !feat.unlocked) return `需本体达 ${feat.min_major}`
  return '开启后道友可邀请化身助战；关闭为闭关'
})

async function onToggle(val: string | number | boolean): Promise<void> {
  const next = Boolean(val)
  if (!unlocked.value) {
    enabled.value = false
    ElMessage.warning(lockHint.value)
    return
  }
  busy.value = true
  try {
    const envelope = await setAvatarAssistSettings(next)
    if (envelope.code !== 0) {
      ElMessage.error(envelope.message || '开关失败')
      enabled.value = !next
      emit('log', envelope.message || '化身助战开关失败', 'warning')
      return
    }
    const data = envelope.data
    enabled.value = Boolean(data?.assist_friends_enabled ?? data?.enabled ?? next)
    if (avatarStore.avatar) {
      avatarStore.setAvatar({
        ...avatarStore.avatar,
        assist_friends_enabled: enabled.value,
        assist_stamina: data?.assist_stamina ?? avatarStore.avatar.assist_stamina,
      })
    }
    const msg = data?.message || (next ? '已开启化身助战' : '已关闭化身助战（闭关）')
    ElMessage.success(msg)
    emit('log', msg, 'success')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-tooltip :content="lockHint" placement="bottom" :show-after="200">
    <el-switch
      v-model="enabled"
      size="small"
      :loading="busy"
      :disabled="busy || !unlocked"
      inline-prompt
      active-text="助战"
      inactive-text="闭关"
      @change="onToggle"
    />
  </el-tooltip>
</template>
