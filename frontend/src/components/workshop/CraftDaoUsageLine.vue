<script setup lang="ts">
/**
 * 开工旁「赋予道韵」勾选：扣当前队列主体道值，为造物附加本命道之力。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useDaoStore } from '../../stores/dao'
import { useCraftStore } from '../../stores/craft'
import { useCharacterStore } from '../../stores/character'
import { useAvatarStore } from '../../stores/avatar'

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const props = defineProps<{
  modelValue: boolean
  /** 仅列表首项拉预览，避免每个配方各打一次 */
  loadPreview?: boolean
}>()

const route = useRoute()
const daoStore = useDaoStore()
const craftStore = useCraftStore()
const characterStore = useCharacterStore()
const avatarStore = useAvatarStore()

const previewHint = ref('')

const hasFate = computed(() => {
  if (craftStore.actor === 'avatar') {
    return Boolean(avatarStore.avatar?.dao?.fate_dao_id)
  }
  const d = characterStore.character?.dao ?? daoStore.me
  return Boolean(d?.fate_dao_id)
})

const disabledReason = computed(() => {
  if (craftStore.actor === 'avatar') {
    if (!avatarStore.avatar) return '尚未凝练化身'
    if (!avatarStore.avatar.dao?.fate_dao_id) return '化身请先开道'
    return ''
  }
  if (!hasFate.value) return '请先开道'
  return ''
})

function toPlayerHint(raw: string): string {
  if (/field required/i.test(raw)) {
    return '预览参数不完整，请刷新后重试'
  }
  return raw
}

const tooltip = computed(() => {
  if (disabledReason.value) return disabledReason.value
  if (previewHint.value) return previewHint.value
  return '消耗当前队列主体的道值，为造物附加本命道之力'
})

async function refreshPreview(on: boolean): Promise<void> {
  if (!props.loadPreview) return
  if (!on) {
    previewHint.value = ''
    return
  }
  const err = await daoStore.loadUsagePreview('craft', craftStore.actor)
  if (err) {
    previewHint.value = toPlayerHint(err)
    return
  }
  const p = daoStore.usagePreview
  previewHint.value = p
    ? `耗道值 ${p.qi_cost}${p.craft_hint || p.effect_label ? ` · ${p.craft_hint || p.effect_label}` : ''}`
    : ''
}

watch(
  () => [props.modelValue, craftStore.actor, props.loadPreview] as const,
  ([on]) => {
    void refreshPreview(Boolean(on))
  },
)

watch(
  () => craftStore.actor,
  async (who) => {
    if (who === 'avatar' && !avatarStore.avatar) {
      await avatarStore.load()
    }
  },
  { immediate: true },
)

onMounted(() => {
  if (route.query.use_dao === '1' || daoStore.preferCraftUseDao) {
    if (hasFate.value) emit('update:modelValue', true)
  }
  if (props.modelValue) {
    void refreshPreview(true)
  }
})

function onChange(v: string | number | boolean): void {
  emit('update:modelValue', Boolean(v))
}
</script>

<template>
  <el-tooltip :content="tooltip" placement="top" :show-after="200">
    <span class="dao-check-wrap">
      <el-checkbox
        :model-value="modelValue"
        :disabled="Boolean(disabledReason)"
        @change="onChange"
      >
        赋予道韵
      </el-checkbox>
    </span>
  </el-tooltip>
</template>

<style scoped>
.dao-check-wrap {
  display: inline-flex;
  align-items: center;
  white-space: nowrap;
}
</style>
