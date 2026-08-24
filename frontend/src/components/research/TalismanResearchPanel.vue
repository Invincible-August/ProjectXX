<script setup lang="ts">
/**
 * Talisman research workbench: materials + whitelist effect → finalize (M8 R4).
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { usePlayWriteGate } from '../../composables/usePlayWriteGate'
import { useResearchStore } from '../../stores/research'
import { useInventoryStore } from '../../stores/inventory'
import { useCharacterStore } from '../../stores/character'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const researchStore = useResearchStore()
const inventoryStore = useInventoryStore()
const characterStore = useCharacterStore()
const { writeBlocked } = usePlayWriteGate()

const selectedIds = ref<string[]>([])
const qty = ref(1)
const effectId = ref('')
const labelZh = ref('')
const busy = ref(false)

const catalog = computed(() => researchStore.catalog)
const talCfg = computed(() => catalog.value?.talisman)
const session = computed(() => researchStore.session)
const effects = computed(() => talCfg.value?.effects || [])
const materials = computed(() => talCfg.value?.allowed_materials || [])
const anyMaterialHeld = computed(() => materials.value.some((id) => materialQty(id) > 0))

watch(
  effects,
  (list) => {
    if (!effectId.value && list.length) {
      effectId.value = list[0].id
    }
  },
  { immediate: true },
)

function materialQty(itemId: string): number {
  return inventoryStore.items
    .filter((i) => i.item_id === itemId)
    .reduce((sum, i) => sum + Number(i.quantity || 0), 0)
}

function materialLabel(itemId: string): string {
  const row = inventoryStore.items.find((i) => i.item_id === itemId)
  return row?.name || itemId
}

function toggleMaterial(id: string): void {
  if (writeBlocked.value) return
  if (selectedIds.value.includes(id)) {
    selectedIds.value = selectedIds.value.filter((x) => x !== id)
  } else {
    selectedIds.value = [...selectedIds.value, id]
  }
}

function effectLabel(id: string): string {
  return effects.value.find((e) => e.id === id)?.label_zh || id
}

async function onCreate(): Promise<void> {
  if (writeBlocked.value) return
  if (!talCfg.value) return
  if (!selectedIds.value.length) {
    ElMessage.info('请选择至少一种材料')
    return
  }
  if (!effectId.value) {
    ElMessage.info('请选择白名单效果')
    return
  }
  busy.value = true
  try {
    const err = await researchStore.create({
      kind: 'talisman',
      materials: selectedIds.value.map((item_id) => ({ item_id, quantity: qty.value })),
      spends: {
        cultivation_points: talCfg.value.spend.cultivation_points,
      },
      effect_id: effectId.value,
    })
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    emit('log', `已开符箓草案：${effectLabel(effectId.value)}`, 'success')
    await inventoryStore.load()
  } finally {
    busy.value = false
  }
}

async function onSaveEffect(): Promise<void> {
  if (writeBlocked.value) return
  if (!effectId.value) return
  busy.value = true
  try {
    const err = await researchStore.saveTalismanDraft(effectId.value)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    emit('log', '已保存效果草案', 'info')
  } finally {
    busy.value = false
  }
}

async function onFinalize(): Promise<void> {
  if (writeBlocked.value) return
  if (!labelZh.value.trim()) {
    ElMessage.info('请先填写中文名称')
    return
  }
  try {
    await ElMessageBox.confirm('定稿后不可再改此稿，只能另开新研。', '确认定稿', {
      type: 'warning',
      confirmButtonText: '定稿',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  busy.value = true
  try {
    if (session.value && effectId.value && session.value.effect_id !== effectId.value) {
      const saveErr = await researchStore.saveTalismanDraft(effectId.value)
      if (saveErr) {
        ElMessage.error(saveErr)
        emit('log', saveErr, 'warning')
        return
      }
    }
    const err = await researchStore.finalize(labelZh.value.trim())
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success('定稿成功')
    emit('log', '符箓图纸已定稿', 'success')
    labelZh.value = ''
    researchStore.clearSession()
  } finally {
    busy.value = false
  }
}

async function onReview(): Promise<void> {
  if (writeBlocked.value) return
  const msg = await researchStore.submitReview()
  ElMessage.info(msg || '审核池尚未开放，后续将开放')
  emit('log', msg || '审核池尚未开放，后续将开放', 'warning')
}

onMounted(() => {
  void inventoryStore.load()
})
</script>

<template>
  <div class="talisman-research">
    <el-card shadow="never">
      <template #header>
        <el-text tag="b" size="small">投入</el-text>
      </template>
      <el-text v-if="talCfg?.help_zh" size="small" type="info" class="help">
        {{ talCfg.help_zh }}
      </el-text>
      <el-form label-width="5rem" size="small">
        <el-form-item label="效果">
          <el-select
            v-model="effectId"
            placeholder="白名单效果"
            style="max-width: 16rem"
            :disabled="writeBlocked"
          >
            <el-option
              v-for="eff in effects"
              :key="eff.id"
              :label="eff.label_zh"
              :value="eff.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="effects.find((e) => e.id === effectId)?.help_zh" label="说明">
          <el-text size="small" type="info">
            {{ effects.find((e) => e.id === effectId)?.help_zh }}
          </el-text>
        </el-form-item>
        <el-form-item label="材料">
          <div class="bag">
            <el-check-tag
              v-for="id in materials"
              :key="id"
              :checked="selectedIds.includes(id)"
              :disabled="writeBlocked"
              @change="toggleMaterial(id)"
            >
              {{ materialLabel(id) }}（持有 {{ materialQty(id) }}）
            </el-check-tag>
            <el-text v-if="!materials.length" size="small" type="info">暂无可用材料配置</el-text>
            <el-text v-else-if="!anyMaterialHeld" size="small" type="warning">
              背包暂无自研材料，可回大厅用 GM「发材料」或去工坊炼制
            </el-text>
          </div>
        </el-form-item>
        <el-form-item label="每种数量">
          <el-input-number v-model="qty" :min="1" :max="99" :disabled="writeBlocked" />
        </el-form-item>
        <el-form-item label="修为">
          <el-text size="small">
            投入 {{ talCfg?.spend.cultivation_points ?? 0 }}
            （当前 {{ characterStore.character?.cultivation_points ?? 0 }}）
          </el-text>
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            size="small"
            :loading="busy"
            :disabled="writeBlocked"
            @click="onCreate"
          >
            开研草案
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <el-text tag="b" size="small">草案与定稿</el-text>
      </template>
      <el-empty
        v-if="!session || session.kind !== 'talisman' || session.phase === 'finalized'"
        description="尚无符箓草案。自研产出仅自己可用；定稿后不可改，只能另开新稿"
        :image-size="56"
      />
      <template v-else>
        <el-text size="small">
          当前效果：{{ effectLabel(session.effect_id || effectId) }}
        </el-text>
        <el-select
          v-model="effectId"
          size="small"
          placeholder="改选效果"
          class="name-input"
          :disabled="writeBlocked"
          @change="onSaveEffect"
        >
          <el-option
            v-for="eff in effects"
            :key="eff.id"
            :label="eff.label_zh"
            :value="eff.id"
          />
        </el-select>
        <el-input
          v-model="labelZh"
          size="small"
          maxlength="16"
          show-word-limit
          placeholder="定稿中文名"
          class="name-input"
          :disabled="writeBlocked"
        />
        <div class="actions">
          <el-button
            type="primary"
            size="small"
            :loading="busy"
            :disabled="writeBlocked"
            @click="onFinalize"
          >
            定稿
          </el-button>
          <el-button size="small" :disabled="writeBlocked" @click="onReview">提交审核</el-button>
        </div>
      </template>
    </el-card>
  </div>
</template>

<style scoped>
.talisman-research {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.help {
  display: block;
  margin-bottom: 0.75rem;
}
.bag {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.name-input {
  max-width: 16rem;
  margin: 0.5rem 0;
  display: block;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
</style>
