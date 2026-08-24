<script setup lang="ts">
/**
 * Technique research workbench: materials → preview → finalize (M8 R2).
 */
import { computed, onMounted, ref } from 'vue'
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
const qty = ref(2)
const labelZh = ref('')
const busy = ref(false)

const catalog = computed(() => researchStore.catalog)
const session = computed(() => researchStore.session)
const canReroll = computed(() => {
  const max = catalog.value?.technique.reroll.max_rerolls ?? 0
  const used = session.value?.reroll_count ?? 0
  return Boolean(session.value && session.value.phase === 'previewed' && used < max)
})

const materials = computed(() => catalog.value?.technique.allowed_materials || [])
const anyMaterialHeld = computed(() => materials.value.some((id) => materialQty(id) > 0))

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

async function onCreate(): Promise<void> {
  if (writeBlocked.value) return
  if (!catalog.value) return
  if (!selectedIds.value.length) {
    ElMessage.info('请选择至少一种材料')
    return
  }
  busy.value = true
  try {
    const err = await researchStore.create({
      kind: 'technique',
      materials: selectedIds.value.map((item_id) => ({ item_id, quantity: qty.value })),
      spends: {
        cultivation_points: catalog.value.technique.spend.cultivation_points,
      },
    })
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    emit('log', '已预览词条', 'success')
    await inventoryStore.load()
  } finally {
    busy.value = false
  }
}

async function onReroll(): Promise<void> {
  if (writeBlocked.value) return
  busy.value = true
  try {
    const err = await researchStore.reroll()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    emit('log', '已重投词条', 'info')
    await inventoryStore.load()
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
    const err = await researchStore.finalize(labelZh.value.trim())
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success('定稿成功')
    emit('log', '功法已定稿', 'success')
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
  <div class="tech-research">
    <el-card shadow="never">
      <template #header>
        <el-text tag="b" size="small">投入</el-text>
      </template>
      <el-text v-if="catalog?.technique.help_zh" size="small" type="info" class="help">
        {{ catalog.technique.help_zh }}
      </el-text>
      <el-form label-width="5rem" size="small">
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
            投入 {{ catalog?.technique.spend.cultivation_points ?? 0 }}
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
            开研预览
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <el-text tag="b" size="small">预览与定稿</el-text>
      </template>
      <el-empty
        v-if="!session || session.phase === 'finalized'"
        description="尚无预览稿。自研产出仅自己可用；定稿后不可改，只能另开新稿"
        :image-size="56"
      />
      <template v-else>
        <el-text size="small">{{ session.dice?.label_zh }}</el-text>
        <div class="tags">
          <el-tag v-for="affix in session.affix_previews" :key="affix.id" size="small">
            {{ affix.label_zh }}
          </el-tag>
        </div>
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
          <el-button size="small" :disabled="!canReroll || busy || writeBlocked" @click="onReroll">
            重投
          </el-button>
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
.tech-research {
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
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin: 0.5rem 0;
}
.name-input {
  max-width: 16rem;
  margin-bottom: 0.5rem;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
</style>
