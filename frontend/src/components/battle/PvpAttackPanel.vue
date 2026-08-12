<script setup lang="ts">
/**
 * PVP 面板：对手列表 / 目标 id 输入 / 快照预览 / 开战。
 *
 * 攻打的是对方「防守快照」（异步非对称），对方零打扰、零损失。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchOpponentsApi } from '../../api/battle'
import { previewSnapshotApi } from '../../api/snapshot'
import { useBattleStore } from '../../stores/battle'
import { useCharacterStore } from '../../stores/character'
import type { OpponentInfo } from '../../types/autochess'
import type { SnapshotPreviewPayload } from '../../types/formation'

const emit = defineEmits<{
  fought: []
}>()

const battleStore = useBattleStore()
const characterStore = useCharacterStore()

const opponents = ref<OpponentInfo[]>([])
const targetId = ref<number | null>(null)
const preview = ref<SnapshotPreviewPayload | null>(null)
const previewing = ref(false)

const isCultivating = computed(() => {
  const direction = characterStore.character?.idle_direction
  return Boolean(direction && direction !== 'none')
})

async function loadOpponents(): Promise<void> {
  const envelope = await fetchOpponentsApi()
  if (envelope.code === 0 && envelope.data) {
    opponents.value = envelope.data.opponents
  }
}

/** 预览目标快照（40048 = 无快照）。 */
async function onPreview(): Promise<void> {
  if (!targetId.value) {
    ElMessage.warning('请先选择或输入目标角色 id')
    return
  }
  previewing.value = true
  preview.value = null
  try {
    const envelope = await previewSnapshotApi(targetId.value)
    if (envelope.code !== 0 || !envelope.data) {
      ElMessage.warning(envelope.message || '目标无有效防守快照')
      return
    }
    preview.value = envelope.data
  } finally {
    previewing.value = false
  }
}

async function onAttack(): Promise<void> {
  if (!targetId.value) {
    ElMessage.warning('请先选择或输入目标角色 id')
    return
  }
  if (isCultivating.value) {
    ElMessage.warning('修炼中不可开战，请先停止修炼')
    return
  }
  const error = await battleStore.startPvp(targetId.value)
  if (error) {
    ElMessage.error(error)
    return
  }
  const result = battleStore.lastReport
  ElMessage[result?.result === 'win' ? 'success' : 'warning'](
    result?.result === 'win' ? '进攻方胜！' : '防守方胜',
  )
  emit('fought')
}

onMounted(() => {
  void loadOpponents()
})
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">攻打快照（PVP）</el-text>
    </template>

    <div class="pvp-form">
      <el-select
        v-model="targetId"
        size="small"
        class="pvp-select"
        placeholder="选择对手"
        filterable
      >
        <el-option
          v-for="opponent in opponents"
          :key="opponent.character_id"
          :value="opponent.character_id"
          :label="`${opponent.dao_name}（id=${opponent.character_id}${opponent.has_snapshot ? '' : ' · 未布防'}）`"
        />
      </el-select>
      <el-button size="small" :loading="previewing" @click="onPreview">
        预览快照
      </el-button>
      <el-button
        type="danger"
        size="small"
        :loading="battleStore.fighting"
        :disabled="isCultivating"
        @click="onAttack"
      >
        攻打
      </el-button>
    </div>

    <el-descriptions v-if="preview" :column="2" size="small" border class="pvp-preview">
      <el-descriptions-item label="道号">{{ preview.dao_name }}</el-descriptions-item>
      <el-descriptions-item label="境界">{{ preview.realm.label }}</el-descriptions-item>
      <el-descriptions-item label="阵法">
        {{ preview.formation_name || preview.formation_id }}
      </el-descriptions-item>
      <el-descriptions-item label="棋子数">{{ preview.units.length }}</el-descriptions-item>
      <el-descriptions-item label="快照时间" :span="2">
        {{ preview.updated_at ? new Date(preview.updated_at).toLocaleString() : '—' }}
      </el-descriptions-item>
    </el-descriptions>

    <el-text type="info" size="small" class="pvp-hint">
      攻打的是对方防守快照，对方不受任何损失；胜负奖励为占位数值。
    </el-text>
  </el-card>
</template>

<style scoped>
.pvp-form {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.pvp-select {
  min-width: 220px;
}

.pvp-preview {
  margin-bottom: 0.5rem;
}

.pvp-hint {
  display: block;
}
</style>
