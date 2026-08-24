<script setup lang="ts">
/**
 * Workshop scribe band: paint finalized private talismans into the bag (M8 R4).
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { scribeTalismanApi } from '../../api/craft'
import { usePlayWriteGate } from '../../composables/usePlayWriteGate'
import { useCharacterStore } from '../../stores/character'
import { useInventoryStore } from '../../stores/inventory'
import { useResearchStore } from '../../stores/research'
import { alertIfIdleBlocked } from '../../utils/idleBlockDialog'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
  scribed: []
}>()

const router = useRouter()
const researchStore = useResearchStore()
const inventoryStore = useInventoryStore()
const characterStore = useCharacterStore()
const { writeBlocked } = usePlayWriteGate()

const templateId = ref('')
const quantity = ref(1)
const busy = ref(false)

const mine = computed(() => researchStore.mine.filter((row) => row.kind === 'talisman'))
const maxBatch = computed(() => researchStore.catalog?.talisman?.scribe.max_batch ?? 20)
const paperId = computed(() => researchStore.catalog?.talisman?.scribe.paper_item_id || 'talisman_paper')
const paperPer = computed(() => researchStore.catalog?.talisman?.scribe.paper_per_copy ?? 1)

const paperHeld = computed(() =>
  inventoryStore.items
    .filter((i) => i.item_id === paperId.value)
    .reduce((sum, i) => sum + Number(i.quantity || 0), 0),
)

onMounted(async () => {
  if (!researchStore.catalog) {
    await researchStore.loadCatalog()
  }
  if (!researchStore.mine.length) {
    await researchStore.loadMine()
  }
  if (!templateId.value && mine.value.length) {
    templateId.value = mine.value[0].id
  }
})

async function onScribe(): Promise<void> {
  if (writeBlocked.value) return
  if (await alertIfIdleBlocked(characterStore.character, '制符')) {
    emit('log', '修炼中无法制符，请先停止修炼', 'warning')
    return
  }
  if (!templateId.value) {
    ElMessage.info('请先在研究室定稿一张符箓图纸')
    return
  }
  busy.value = true
  try {
    const envelope = await scribeTalismanApi({
      template_id: templateId.value,
      quantity: quantity.value,
    })
    if (envelope.code !== 0 || !envelope.data) {
      ElMessage.error(envelope.message || '画符失败')
      emit('log', envelope.message || '画符失败', 'warning')
      return
    }
    ElMessage.success(`已画 ${envelope.data.quantity} 张${envelope.data.label_zh}`)
    emit('log', `画符 ${envelope.data.label_zh} ×${envelope.data.quantity}`, 'success')
    await inventoryStore.load()
    emit('scribed')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never" class="scribe-card">
    <template #header>
      <el-text tag="b" size="small">画符</el-text>
    </template>
    <el-empty v-if="!mine.length" description="尚无自研符箓图纸，请先去研究室定稿" :image-size="48">
      <el-button size="small" @click="router.push('/cave/lab?mode=talisman')">去研究室</el-button>
    </el-empty>
    <el-form v-else label-width="5rem" size="small">
      <el-form-item label="图纸">
        <el-select v-model="templateId" placeholder="选择图纸" :disabled="writeBlocked">
          <el-option
            v-for="row in mine"
            :key="row.id"
            :label="row.label_zh"
            :value="row.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="数量">
        <el-input-number v-model="quantity" :min="1" :max="maxBatch" :disabled="writeBlocked" />
      </el-form-item>
      <el-form-item label="符纸">
        <el-text size="small">
          消耗 {{ paperPer * quantity }}（持有 {{ paperHeld }}）
        </el-text>
      </el-form-item>
      <el-form-item>
        <el-button
          type="primary"
          size="small"
          :loading="busy"
          :disabled="writeBlocked"
          @click="onScribe"
        >
          画符
        </el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<style scoped>
.scribe-card {
  min-width: 0;
}
</style>
