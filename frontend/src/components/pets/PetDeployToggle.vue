<script setup lang="ts">
/**
 * 灵宠布阵偏好勾选（不直接改预设坐标）。
 */
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { usePetsStore } from '../../stores/pets'
import type { PetPublic } from '../../types/pets'

const props = defineProps<{
  pet: PetPublic
}>()

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const petsStore = usePetsStore()
const preferred = ref(props.pet.is_deploy_preferred)
const busy = ref(false)

watch(
  () => props.pet.is_deploy_preferred,
  (v) => {
    preferred.value = v
  },
)

async function onToggle(val: boolean): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const error = await petsStore.setDeployPreferred(props.pet.id, val)
    if (error) {
      preferred.value = !val
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    emit('log', val ? '已设为偏好上阵' : '已取消偏好上阵', 'info')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-checkbox
    :model-value="preferred"
    :disabled="busy"
    @update:model-value="(v: boolean) => { preferred = v; void onToggle(v) }"
  >
    偏好上阵（布阵候选栏优先展示）
  </el-checkbox>
</template>
