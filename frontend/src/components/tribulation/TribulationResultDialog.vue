<script setup lang="ts">
/**
 * 渡劫结果弹窗：成功 / 失败 / 陨落。
 * 成功：主按钮「确认突破」回大厅；陨落：前往引渡。
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useCharacterStore } from '../../stores/character'
import type { TribulationSessionPublic } from '../../types/tribulation'

const props = defineProps<{
  visible: boolean
  session: TribulationSessionPublic | null
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
}>()

const router = useRouter()
const characterStore = useCharacterStore()

const title = computed(() => {
  const p = props.session?.phase
  if (p === 'won') return '渡劫成功 · 确认突破'
  if (p === 'fallen') return '陨落·待引渡'
  if (p === 'failed') return '渡劫失败'
  return '渡劫结果'
})

const message = computed(() => {
  const p = props.session?.phase
  if (p === 'won') {
    return `雷劫已圆满。境界已进阶至：${props.session?.target_label || ''} · 品阶 ${props.session?.projected_grade || '—'}。点击「确认突破」返回大厅查看新境界。`
  }
  if (p === 'fallen') {
    return '极端失败，魂飞魄散，已进入待引渡。可前往轮回与引渡页自救或入轮回。'
  }
  if (p === 'failed') {
    return '渡劫失败，已施加可见惩罚。'
  }
  return ''
})

/** 需要引导去引渡页：陨落，或角色状态已是待引渡 */
const showFerryCta = computed(() => {
  if (props.session?.phase === 'fallen') return true
  return characterStore.character?.status === 'awaiting_ferry'
})

const showBreakthroughCta = computed(() => props.session?.phase === 'won')

function onClose(): void {
  emit('update:visible', false)
}

function onFerry(): void {
  emit('update:visible', false)
  void router.push({ name: 'reincarnation', query: { mode: 'ferry' } })
}

/** 渡劫成功：确认突破并回大厅 */
function onConfirmBreakthrough(): void {
  emit('update:visible', false)
  void router.push({ name: 'hall' })
}

function onHall(): void {
  emit('update:visible', false)
  void router.push({ name: 'hall' })
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="title"
    width="440px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:visible', $event)"
  >
    <el-text>{{ message }}</el-text>
    <template #footer>
      <el-button v-if="showFerryCta" type="warning" @click="onFerry">
        前往轮回与引渡
      </el-button>
      <el-button
        v-if="showBreakthroughCta"
        type="primary"
        @click="onConfirmBreakthrough"
      >
        确认突破
      </el-button>
      <el-button v-else-if="!showFerryCta" type="primary" @click="onHall">
        回大厅
      </el-button>
      <el-button @click="onClose">关闭</el-button>
    </template>
  </el-dialog>
</template>
