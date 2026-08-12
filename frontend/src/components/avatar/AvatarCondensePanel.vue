<script setup lang="ts">
/**
 * 化身凝练面板：门槛 / 费用 / 按钮闸一律读后端 ``features.condense``。
 * POST /condense 仍会再校验；前端不再本地抄写境界序。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAvatarStore } from '../../stores/avatar'
import { useCharacterStore } from '../../stores/character'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const avatarStore = useAvatarStore()
const characterStore = useCharacterStore()
const busy = ref(false)
const flash = ref(false)

/** 后端权威闸；缺省时先禁用并触发补拉 */
const gate = computed(() => avatarStore.features?.condense ?? null)

const canCondense = computed(() => Boolean(gate.value?.can_condense))

const condenseHint = computed(() => {
  const ch = characterStore.character
  if (!ch) return ''
  if (gate.value?.block_message) return gate.value.block_message
  if (ch.has_avatar) return '已凝练化身'
  if (!gate.value) return '正在同步凝练条件…'
  const cost = gate.value.spirit_stone_cost
  return `凝练需消耗 ${cost} 灵石`
})

onMounted(async () => {
  // 未凝练进入本面板时，务必有权威闸（避免仅靠 /me=null）
  if (!avatarStore.features?.condense) {
    await avatarStore.loadFeatures()
  }
})

async function onCondense(): Promise<void> {
  if (busy.value || !canCondense.value) return
  busy.value = true
  try {
    const error = await avatarStore.condense()
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      // 失败后刷新闸（灵石/境界可能已变）
      await avatarStore.loadFeatures()
      return
    }
    ElMessage.success('化身凝练完成；可并行安排挂机')
    emit('log', '化身凝练完成；可并行安排挂机', 'success')
    flash.value = true
    setTimeout(() => {
      flash.value = false
    }, 1500)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never" :class="{ 'condense-flash': flash }">
    <template #header>
      <el-text tag="b">凝练化身</el-text>
    </template>

    <el-text type="info" size="small" class="hint">
      金丹境及以上可凝练第二线程：化身可独立挂机，与本体并行结算。
    </el-text>

    <el-alert
      :title="condenseHint"
      :type="canCondense ? 'info' : 'warning'"
      show-icon
      :closable="false"
      class="alert"
    />

    <el-button
      type="primary"
      :loading="busy"
      :disabled="!canCondense"
      @click="onCondense"
    >
      凝练化身
    </el-button>
  </el-card>
</template>

<style scoped>
.hint {
  display: block;
  margin-bottom: 0.75rem;
}

.alert {
  margin-bottom: 0.75rem;
}

.condense-flash {
  animation: flash-bg 1.2s ease;
}

@keyframes flash-bg {
  0% {
    box-shadow: 0 0 0 0 rgba(103, 194, 58, 0.6);
  }
  50% {
    box-shadow: 0 0 16px 4px rgba(103, 194, 58, 0.35);
  }
  100% {
    box-shadow: none;
  }
}
</style>
