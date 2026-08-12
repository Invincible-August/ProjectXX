<script setup lang="ts">
/**
 * 资源分配：投入境界进度或升功法（系统不代选）。
 */
import { computed, onMounted, ref } from 'vue'
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
const tab = ref<'realm' | 'technique'>('realm')
const amount = ref(50)
const techniques = ref<TechniqueItem[]>([])
const selectedTechId = ref('')

const poolByTrack = computed(() => {
  const ch = character.value
  if (!ch) return { spirit: 0, body: 0, crafting: 0 }
  return {
    spirit: ch.cultivation_points,
    body: ch.body_tempering_points,
    crafting: ch.crafting_exp,
  }
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
        挂机只涨资源池；境界进度与功法需手动投入（系统不代选）。
        下方池数字为服务端已入账（不含片内推算）。
      </el-text>

      <el-descriptions v-if="character" :column="1" size="small" class="pools">
        <el-descriptions-item label="修为池">{{ poolByTrack.spirit }}</el-descriptions-item>
        <el-descriptions-item label="炼体度池">{{ poolByTrack.body }}</el-descriptions-item>
        <el-descriptions-item label="制造业经验池">
          {{ poolByTrack.crafting }}
        </el-descriptions-item>
        <el-descriptions-item label="境界进度">
          {{ character.realm_progress }}
          <template v-if="character.cultivation_to_next != null">
            / {{ character.cultivation_to_next }}
          </template>
        </el-descriptions-item>
      </el-descriptions>

      <el-radio-group v-model="tab" size="small" class="tabs">
        <el-radio-button value="realm">投入境界</el-radio-button>
        <el-radio-button value="technique">升功法</el-radio-button>
      </el-radio-group>

      <el-form label-position="top" size="small" class="form">
        <el-form-item v-if="tab === 'technique'" label="功法">
          <el-select v-model="selectedTechId" style="width: 100%">
            <el-option
              v-for="t in techniques"
              :key="t.id"
              :label="`${t.name} Lv.${t.level}/${t.max_level}（${t.track}）`"
              :value="t.id"
            />
          </el-select>
          <el-text
            v-if="techniques.find((t) => t.id === selectedTechId)?.next_cost != null"
            size="small"
            type="info"
          >
            下一级需
            {{ techniques.find((t) => t.id === selectedTechId)?.next_cost }}
            点对应池
          </el-text>
        </el-form-item>
        <el-form-item :label="tab === 'realm' ? '投入修为池点数' : '投入池点数'">
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

.pools {
  margin-bottom: 0.5rem;
}

.tabs {
  margin-bottom: 0.5rem;
}

.form {
  margin-top: 0.25rem;
}
</style>
