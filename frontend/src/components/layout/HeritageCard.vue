<script setup lang="ts">
/**
 * 发机缘表单（机缘卡片在聊天消息流中展示）。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useCharacterStore } from '../../stores/character'
import { useHeritageStore } from '../../stores/heritage'
import { useInventoryStore } from '../../stores/inventory'

const props = defineProps<{
  channelRef: string | null
  canSend: boolean
}>()

const emit = defineEmits<{
  created: []
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const heritageStore = useHeritageStore()
const inventoryStore = useInventoryStore()
const characterStore = useCharacterStore()

const showForm = ref(false)
const mode = ref<'random' | 'fixed'>('random')
const shareCount = ref(2)
/** 内容类型：灵石 或 背包物品（二选一） */
const contentKind = ref<'spirit' | 'item'>('spirit')
const spiritStones = ref(100)
const selectedItemId = ref<string | null>(null)
const itemQty = ref(1)
const noteZh = ref('')

const ownedSpirit = computed(() => Number(characterStore.character?.spirit_stones ?? 0))

/**
 * 普通袋中可发机缘的物品：非绑定、非唯一、可交易；按 item_id 汇总数量。
 */
const eligibleBagOptions = computed(() => {
  const byId = new Map<
    string,
    { item_id: string; name: string; quantity: number }
  >()
  for (const row of inventoryStore.normalItems) {
    if (row.bound === true) continue
    if (row.unique === true) continue
    if (row.tradable !== true) continue
    const prev = byId.get(row.item_id)
    if (prev) {
      prev.quantity += Number(row.quantity || 0)
    } else {
      byId.set(row.item_id, {
        item_id: row.item_id,
        name: row.name || row.item_id,
        quantity: Number(row.quantity || 0),
      })
    }
  }
  return [...byId.values()]
    .filter((x) => x.quantity > 0)
    .sort((a, b) => a.name.localeCompare(b.name, 'zh'))
})

const selectedOption = computed(
  () =>
    eligibleBagOptions.value.find((x) => x.item_id === selectedItemId.value) ??
    null,
)

const selectedMaxQty = computed(() => Math.max(1, selectedOption.value?.quantity ?? 1))

watch(
  () => props.channelRef,
  (ref) => {
    // 发机缘组件仅挂在世界/宗门；列表刷新由 ChatDock 统一按频控制
    if (ref) void heritageStore.refresh(ref)
  },
  { immediate: true },
)

watch(selectedItemId, () => {
  itemQty.value = 1
})

watch(contentKind, (kind) => {
  if (kind === 'spirit') {
    selectedItemId.value = null
    itemQty.value = 1
  } else {
    spiritStones.value = 0
  }
})

/**
 * 展开/收起发机缘表单。
 */
async function toggleForm(): Promise<void> {
  showForm.value = !showForm.value
  if (showForm.value) {
    const err = await inventoryStore.load()
    if (err) ElMessage.warning(err)
  }
}

async function onCreate(): Promise<void> {
  if (!props.channelRef) {
    ElMessage.warning('请先选择频道')
    return
  }
  if (!props.canSend) {
    ElMessage.warning('当前频道不可发机缘')
    return
  }

  let stones = 0
  let items: Array<{ item_id: string; quantity: number }> = []

  if (contentKind.value === 'spirit') {
    stones = Math.max(0, Math.floor(Number(spiritStones.value) || 0))
    if (stones <= 0) {
      ElMessage.warning('请填写要发放的灵石数量')
      return
    }
    if (stones > ownedSpirit.value) {
      ElMessage.warning(`灵石不足（现有 ${ownedSpirit.value}）`)
      return
    }
  } else {
    const opt = selectedOption.value
    const qty = Math.max(0, Math.floor(Number(itemQty.value) || 0))
    if (!opt || !selectedItemId.value) {
      ElMessage.warning('请从背包选择要发放的物品')
      return
    }
    if (qty <= 0) {
      ElMessage.warning('请填写物品数量')
      return
    }
    if (qty > opt.quantity) {
      ElMessage.warning(`数量超出背包（最多 ${opt.quantity}）`)
      return
    }
    items = [{ item_id: opt.item_id, quantity: qty }]
  }

  const err = await heritageStore.create({
    channel_ref: props.channelRef,
    mode: mode.value,
    share_count: shareCount.value,
    spirit_stones: stones,
    items,
    note_zh: noteZh.value || undefined,
  })
  if (err) {
    ElMessage.error(err)
    emit('log', err, 'warning')
    return
  }
  ElMessage.success(heritageStore.lastMessage || '机缘已发出')
  emit('log', heritageStore.lastMessage || '机缘已发出', 'success')
  emit('created')
  showForm.value = false
  noteZh.value = ''
  selectedItemId.value = null
  itemQty.value = 1
  void inventoryStore.load()
}
</script>

<template>
  <div class="heritage-compose">
    <div class="hdr">
      <el-text tag="b" size="small">机缘</el-text>
      <el-button
        size="small"
        type="primary"
        plain
        :disabled="!canSend || !channelRef"
        @click="toggleForm"
      >
        {{ showForm ? '收起' : '发机缘' }}
      </el-button>
    </div>

    <div v-if="showForm" class="form">
      <el-radio-group v-model="mode" size="small">
        <el-radio-button value="random">拼手气</el-radio-button>
        <el-radio-button value="fixed">定额均分</el-radio-button>
      </el-radio-group>

      <div class="row">
        <el-text size="small">份数</el-text>
        <el-input-number v-model="shareCount" :min="1" :max="50" size="small" />
      </div>

      <el-radio-group v-model="contentKind" size="small" class="kind-row">
        <el-radio-button value="spirit">灵石</el-radio-button>
        <el-radio-button value="item">背包物品</el-radio-button>
      </el-radio-group>

      <template v-if="contentKind === 'spirit'">
        <div class="row">
          <el-text size="small">灵石</el-text>
          <el-input-number
            v-model="spiritStones"
            :min="1"
            :max="Math.max(1, ownedSpirit)"
            :step="10"
            size="small"
          />
        </div>
        <el-text size="small" type="info">现有 {{ ownedSpirit }} 灵石</el-text>
      </template>

      <template v-else>
        <el-select
          v-model="selectedItemId"
          size="small"
          filterable
          clearable
          placeholder="从背包选择（非绑定非唯一）"
          :loading="inventoryStore.loading"
          style="width: 100%"
        >
          <el-option
            v-for="opt in eligibleBagOptions"
            :key="opt.item_id"
            :label="`${opt.name} ×${opt.quantity}`"
            :value="opt.item_id"
          />
        </el-select>
        <div class="row">
          <el-text size="small">数量</el-text>
          <el-input-number
            v-model="itemQty"
            :min="1"
            :max="selectedMaxQty"
            size="small"
            :disabled="!selectedItemId"
          />
        </div>
        <el-text v-if="!eligibleBagOptions.length" size="small" type="warning">
          背包暂无可发机缘的物品
        </el-text>
      </template>

      <el-input v-model="noteZh" size="small" placeholder="附言（可选）" maxlength="64" />
      <el-button type="primary" size="small" :loading="heritageStore.loading" @click="onCreate">
        发出
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.heritage-compose {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  border-top: 1px dashed var(--el-border-color-lighter);
  padding-top: 0.35rem;
  flex-shrink: 0;
}
.hdr {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 0.35rem;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  max-height: 200px;
  overflow: auto;
}
.row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.kind-row {
  width: 100%;
}
</style>
