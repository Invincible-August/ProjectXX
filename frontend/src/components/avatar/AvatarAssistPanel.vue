<script setup lang="ts">
/**
 * 化身助战开关 + 独立助战体力槽（与探索/独战体力隔离）。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { setAvatarAssistSettings } from '../../api/avatar'
import type { AvatarAssistStaminaPanel, AvatarPublic } from '../../types/avatar'
import { useAvatarStore } from '../../stores/avatar'

const props = defineProps<{
  avatar: AvatarPublic
}>()

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'error']
}>()

const avatarStore = useAvatarStore()
const busy = ref(false)
const enabled = ref(Boolean(props.avatar.assist_friends_enabled))

watch(
  () => props.avatar.assist_friends_enabled,
  (v) => {
    enabled.value = Boolean(v)
  },
)

const assistStamina = computed<AvatarAssistStaminaPanel | null>(
  () => props.avatar.assist_stamina ?? null,
)

const pct = computed(() => {
  const s = assistStamina.value
  if (!s || s.assist_stamina_cap <= 0) return 0
  return Math.min(100, Math.round((s.assist_stamina / s.assist_stamina_cap) * 100))
})

async function onToggle(val: boolean): Promise<void> {
  busy.value = true
  try {
    const envelope = await setAvatarAssistSettings(val)
    if (envelope.code !== 0) {
      ElMessage.error(envelope.message || '开关失败')
      enabled.value = !val
      emit('log', envelope.message || '化身助战开关失败', 'warning')
      return
    }
    const data = envelope.data
    enabled.value = Boolean(data?.assist_friends_enabled ?? data?.enabled ?? val)
    if (data?.assist_stamina && avatarStore.avatar) {
      avatarStore.setAvatar({
        ...avatarStore.avatar,
        assist_friends_enabled: enabled.value,
        assist_stamina: data.assist_stamina,
      })
    } else {
      await avatarStore.load()
    }
    const msg = data?.message || (val ? '已开启化身助战' : '已关闭化身助战（闭关）')
    ElMessage.success(msg)
    emit('log', msg, 'success')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">化身助战</el-text>
    </template>

    <div class="switch-row">
      <el-switch
        v-model="enabled"
        :loading="busy"
        active-text="开启化身助战"
        inactive-text="关闭（闭关）"
        @change="onToggle"
      />
    </div>
    <el-text size="small" type="info" class="hint">
      开启后道友可「邀请化身」立即助战；关闭时对方会看到「化身正在闭关中」。同时仅可接受一次助战，PVE
      战后自动离队（秘境整场结束后离队）。
    </el-text>

    <template v-if="assistStamina">
      <el-divider content-position="left">助战体力</el-divider>
      <el-progress :percentage="pct" :stroke-width="12" />
      <div class="row">
        <el-text size="small">
          {{ assistStamina.assist_stamina }} / {{ assistStamina.assist_stamina_cap }}
        </el-text>
        <el-text size="small" type="info">
          每场消耗 {{ assistStamina.battle_cost }} · 恢复
          {{ assistStamina.recovery_per_hour }}/时
        </el-text>
      </div>
      <el-text
        v-if="assistStamina.assist_stamina_locked"
        size="small"
        type="warning"
        class="hint"
      >
        助战体力已耗尽，须恢复至 {{ assistStamina.resume_threshold }} 点后方可再助战
      </el-text>
      <el-text v-else size="small" type="info" class="hint">
        独立槽位：不受探索体力与任何加成影响，仅随化身境界提高上限。
      </el-text>
    </template>
  </el-card>
</template>

<style scoped>
.switch-row {
  margin-bottom: 0.5rem;
}

.row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 0.5rem;
}

.hint {
  display: block;
  margin-top: 0.35rem;
  line-height: 1.45;
}
</style>
