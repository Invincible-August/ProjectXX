<script setup lang="ts">
/**
 * 战斗开战区：运用本命道勾选 + preview 说明。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useDaoStore } from '../../stores/dao'
import { useCharacterStore } from '../../stores/character'

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const props = defineProps<{
  modelValue: boolean
}>()

const route = useRoute()
const daoStore = useDaoStore()
const characterStore = useCharacterStore()

const previewHint = ref('')

const hasFate = computed(() => {
  const d = characterStore.character?.dao ?? daoStore.me
  return Boolean(d?.fate_dao_id)
})

const disabledReason = computed(() => {
  if (!hasFate.value) return '请先开道'
  return ''
})

watch(
  () => props.modelValue,
  async (on) => {
    if (!on) {
      previewHint.value = ''
      return
    }
    const err = await daoStore.loadUsagePreview('battle')
    if (err) {
      previewHint.value = err
    } else {
      const p = daoStore.usagePreview
      previewHint.value = p
        ? `耗道值 ${p.qi_cost}${p.battle_hint || p.effect_label ? ` · ${p.battle_hint || p.effect_label}` : ''}`
        : ''
    }
  },
)

onMounted(() => {
  if (route.query.use_dao === '1' || daoStore.preferBattleUseDao) {
    if (hasFate.value) emit('update:modelValue', true)
  }
})

function onChange(v: string | number | boolean): void {
  emit('update:modelValue', Boolean(v))
}
</script>

<template>
  <div class="dao-usage-line">
    <el-checkbox
      :model-value="modelValue"
      :disabled="Boolean(disabledReason)"
      @change="onChange"
    >
      运用本命道
    </el-checkbox>
    <el-text v-if="disabledReason" size="small" type="info">
      {{ disabledReason }}
    </el-text>
    <el-text v-else-if="previewHint" size="small" type="warning">
      {{ previewHint }}
    </el-text>
    <el-text v-else size="small" type="info">
      消耗与效果以服务端预览为准
    </el-text>
  </div>
</template>

<style scoped>
.dao-usage-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin: 0.5rem 0;
}
</style>
