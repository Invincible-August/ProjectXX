<script setup lang="ts">
/**
 * 资源分配：投入境界 / 投入淬体 / 升级功法。
 * 炼体功法（track=body）自动扣淬体度池。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { allocateApi } from '../api/allocate'
import { fetchMyTechniquesApi } from '../api/techniques'
import { useCharacterStore } from '../stores/character'
import type { TechniqueItem } from '../types/techniques'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const characterStore = useCharacterStore()
const character = computed(() => characterStore.character)
const open = ref(true)
const busy = ref(false)
const tab = ref<'realm' | 'body_temper' | 'technique'>('realm')
const amount = ref(50)
const techniques = ref<TechniqueItem[]>([])
const selectedTechId = ref('')

const TRACK_POOL_LABEL: Record<string, string> = {
  spirit: '修为池',
  body: '淬体度池',
  crafting: '制造业经验池',
}

const TRACK_NAME: Record<string, string> = {
  spirit: '灵修',
  body: '炼体',
  crafting: '制造',
}

const poolByTrack = computed(() => {
  const ch = character.value
  if (!ch) return { spirit: 0, body: 0, crafting: 0 }
  return {
    spirit: ch.cultivation_points,
    body: ch.body_tempering_points,
    crafting: ch.crafting_exp,
  }
})

const selectedTech = computed(
  () => techniques.value.find((t) => t.id === selectedTechId.value) ?? null,
)

/** 当前分配将消耗的池说明 */
const activePoolHint = computed(() => {
  if (tab.value === 'realm') {
    return `消耗修为池（现有 ${poolByTrack.value.spirit}）→ 境界进度`
  }
  if (tab.value === 'body_temper') {
    const prog = character.value?.body_temper_progress ?? 0
    const toNext = character.value?.body_temper_to_next
    const needHint =
      toNext == null ? `进度 ${prog}` : `进度 ${prog}，距圆满尚需 ${toNext}`
    return `消耗淬体度池（现有 ${poolByTrack.value.body}）→ 淬体进度（${needHint}）`
  }
  const tech = selectedTech.value
  if (!tech) return '请选择功法'
  const poolLabel = TRACK_POOL_LABEL[tech.track] || '资源池'
  const bal =
    tech.track === 'body'
      ? poolByTrack.value.body
      : tech.track === 'crafting'
        ? poolByTrack.value.crafting
        : poolByTrack.value.spirit
  if (tech.track === 'body') {
    return `当前为炼体功法，自动消耗淬体度池（现有 ${bal}）`
  }
  return `当前为${TRACK_NAME[tech.track] || tech.track}功法，消耗${poolLabel}（现有 ${bal}）`
})

const amountLabel = computed(() => {
  if (tab.value === 'realm') return '投入修为池点数'
  if (tab.value === 'body_temper') return '投入淬体度池点数'
  const tech = selectedTech.value
  if (tech?.track === 'body') return '投入淬体度池点数'
  if (tech?.track === 'crafting') return '投入制造业经验点数'
  return '投入修为池点数'
})

async function loadTechniques(): Promise<void> {
  const envelope = await fetchMyTechniquesApi()
  if (envelope.code === 0 && envelope.data?.items) {
    techniques.value = envelope.data.items
    if (!selectedTechId.value && techniques.value.length) {
      selectedTechId.value = techniques.value[0].id
    }
  }
}

onMounted(() => {
  void loadTechniques()
})

watch(selectedTechId, () => {
  // 切换功法时，若下一级有明确费用，可把投入量对齐（不强制）
  const cost = selectedTech.value?.next_cost ?? selectedTech.value?.cost_next
  if (tab.value === 'technique' && typeof cost === 'number' && cost > 0) {
    amount.value = cost
  }
})

async function submit(): Promise<void> {
  if (busy.value || !character.value) return
  if (character.value.offline_pending) {
    ElMessage.warning('请先领取离线收益')
    return
  }
  if (amount.value < 1) {
    ElMessage.warning('投入量须为正整数')
    return
  }
  if (tab.value === 'technique' && !selectedTechId.value) {
    ElMessage.warning('请选择功法')
    return
  }
  busy.value = true
  try {
    const envelope = await allocateApi({
      target_type: tab.value,
      target_id: tab.value === 'technique' ? selectedTechId.value : null,
      amount: amount.value,
    })
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || `分配失败（code=${envelope.code}）`)
    }
    characterStore.applyCharacter(envelope.data.character)
    ElMessage.success(envelope.data.message || '分配成功')
    emit('log', envelope.data.message || '资源分配成功', 'success')
    await loadTechniques()
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '分配失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never" class="alloc-panel">
    <template #header>
      <div class="alloc-header" @click="open = !open">
        <el-text tag="b">资源分配</el-text>
        <el-text size="small" type="info">{{ open ? '收起' : '展开' }}</el-text>
      </div>
    </template>

    <div v-show="open">
      <el-text size="small" type="info" class="hint">
        挂机只涨资源池；境界 / 淬体进度与功法需手动投入。炼体功法自动扣淬体度池。
      </el-text>

      <el-descriptions v-if="character" :column="1" size="small" class="pools">
        <el-descriptions-item label="修为池">{{ poolByTrack.spirit }}</el-descriptions-item>
        <el-descriptions-item label="淬体度池">{{ poolByTrack.body }}</el-descriptions-item>
        <el-descriptions-item label="制造业经验池">
          {{ poolByTrack.crafting }}
        </el-descriptions-item>
        <el-descriptions-item label="境界进度">
          {{ character.realm_progress }}
          <template v-if="character.cultivation_to_next != null">
            / {{ character.cultivation_to_next }}
          </template>
        </el-descriptions-item>
        <el-descriptions-item label="淬体进度">
          {{ character.body_temper_progress ?? 0 }}
          <template v-if="character.body_temper_to_next != null">
            · 尚需 {{ character.body_temper_to_next }}
          </template>
          <el-text size="small" type="info">
            （{{ character.body_temper_display || character.body_temper_stage_name || '—' }}）
          </el-text>
        </el-descriptions-item>
      </el-descriptions>

      <el-radio-group v-model="tab" size="small" class="tabs">
        <el-radio-button value="realm">投入境界</el-radio-button>
        <el-radio-button value="body_temper">投入淬体</el-radio-button>
        <el-radio-button value="technique">升级功法</el-radio-button>
      </el-radio-group>

      <el-text size="small" type="info" class="pool-hint">{{ activePoolHint }}</el-text>

      <el-form label-position="top" size="small" class="form">
        <el-form-item v-if="tab === 'technique'" label="功法">
          <el-select v-model="selectedTechId" style="width: 100%">
            <el-option
              v-for="t in techniques"
              :key="t.id"
              :label="`${t.name} Lv.${t.level}/${t.max_level}（${TRACK_NAME[t.track] || t.track}·${TRACK_POOL_LABEL[t.track] || '池'}）`"
              :value="t.id"
            />
          </el-select>
          <el-text
            v-if="selectedTech?.next_cost != null || selectedTech?.cost_next != null"
            size="small"
            type="info"
          >
            下一级需
            {{ selectedTech?.next_cost ?? selectedTech?.cost_next }}
            点{{ TRACK_POOL_LABEL[selectedTech?.track || ''] || '对应池' }}
          </el-text>
        </el-form-item>
        <el-form-item :label="amountLabel">
          <el-input-number v-model="amount" :min="1" :step="10" />
        </el-form-item>
        <el-button type="primary" :loading="busy" @click="submit">确认分配</el-button>
      </el-form>
    </div>
  </el-card>
</template>

<style scoped>
.alloc-header {
  display: flex;
  justify-content: space-between;
  cursor: pointer;
  user-select: none;
}

.hint {
  display: block;
  margin-bottom: 0.5rem;
}

.pool-hint {
  display: block;
  margin: 0.35rem 0 0.5rem;
}

.pools {
  margin-bottom: 0.5rem;
}

.tabs {
  margin-bottom: 0.25rem;
}

.form {
  margin-top: 0.25rem;
}
</style>
