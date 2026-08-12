<script setup lang="ts">
/**
 * 渡劫准备格：排序 / 选道具 / 提交 prep。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useInventoryStore } from '../../stores/inventory'
import { useTribulationStore } from '../../stores/tribulation'
import type { TribulationPrepSlot } from '../../types/tribulation'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const tribulationStore = useTribulationStore()
const inventoryStore = useInventoryStore()

const slots = ref<TribulationPrepSlot[]>([])
const formationId = ref<string | null>(null)
const veilSelected = ref(false)
const saving = ref(false)

const session = computed(() => tribulationStore.session)
const maxSlots = computed(() => Math.max(session.value?.prep_slots?.length || 4, 4))

const candidates = computed(() => inventoryStore.items)

watch(
  session,
  (s) => {
    if (!s) return
    slots.value = (s.prep_slots?.length ? [...s.prep_slots] : []).map((slot, i) => ({
      slot: slot.slot ?? i,
      item_uid: slot.item_uid,
      item_name: slot.item_name,
      inefficient: slot.inefficient,
    }))
    while (slots.value.length < maxSlots.value) {
      slots.value.push({ slot: slots.value.length })
    }
    formationId.value = s.formation_id ?? null
    veilSelected.value = Boolean(s.veil_selected)
  },
  { immediate: true },
)

onMounted(() => {
  void inventoryStore.load()
})

function moveSlot(index: number, dir: -1 | 1): void {
  const next = index + dir
  if (next < 0 || next >= slots.value.length) return
  const arr = [...slots.value]
  const tmp = arr[index]!
  arr[index] = arr[next]!
  arr[next] = tmp
  slots.value = arr.map((s, i) => ({ ...s, slot: i }))
}

function assignItem(index: number, itemUid: string | null): void {
  const item = candidates.value.find((c) => c.item_uid === itemUid)
  const next = [...slots.value]
  next[index] = {
    slot: index,
    item_uid: itemUid || undefined,
    item_name: item?.name,
    inefficient:
      item?.item_type === 'artifact' || item?.meta?.tribulation_inefficient === true,
  }
  slots.value = next
}

function onSelectItem(index: number, value: string | number | boolean | undefined): void {
  const uid = value == null || value === '' ? null : String(value)
  assignItem(index, uid)
}

async function onSave(): Promise<void> {
  if (saving.value) return
  saving.value = true
  try {
    const err = await tribulationStore.save({
      slots: slots.value.map((s, i) => ({
        slot: i,
        item_uid: s.item_uid ?? null,
      })),
      formation_id: formationId.value,
      veil_selected: veilSelected.value,
    })
    if (err) throw new Error(err)
    ElMessage.success('准备已保存')
    emit('log', '渡劫准备格已保存', 'success')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '保存失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    saving.value = false
  }
}

async function onCommit(): Promise<void> {
  if (saving.value) return
  saving.value = true
  try {
    const saveErr = await tribulationStore.save({
      slots: slots.value.map((s, i) => ({
        slot: i,
        item_uid: s.item_uid ?? null,
      })),
      formation_id: formationId.value,
      veil_selected: veilSelected.value,
    })
    if (saveErr) throw new Error(saveErr)
    const err = await tribulationStore.commit()
    if (err) throw new Error(err)
    ElMessage.success('准备已确认')
    emit('log', '渡劫准备已确认（committed）', 'success')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '确认失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">准备格（按序消耗）</el-text>
    </template>

    <el-alert
      type="warning"
      :closable="false"
      show-icon
      class="consume-alert"
      title="放入准备格的道具将在开渡后永久消耗，不可取回"
    >
      <template #default>
        <ul class="consume-list">
          <li>确认准备并<strong>开渡</strong>后，格内丹药 / 法宝等立刻从背包扣除。</li>
          <li>雷劫中按格序号依次消耗减伤；普通法宝可抵劫但效率极差。</li>
          <li>未开渡前可清空格子并保存，道具仍留在背包；开渡后无法退还。</li>
        </ul>
      </template>
    </el-alert>

    <el-text size="small" type="info" class="tip">
      格序号 = 消耗顺序；空格可跳过。遮天请在侧栏单独勾选。
    </el-text>

    <div v-for="(slot, index) in slots" :key="index" class="slot-row">
      <el-tag size="small" type="info">格 {{ index + 1 }}</el-tag>
      <el-select
        :model-value="slot.item_uid ?? ''"
        clearable
        filterable
        placeholder="选择道具（开渡后消耗）"
        size="small"
        class="slot-select"
        @clear="assignItem(index, null)"
        @change="onSelectItem(index, $event)"
      >
        <el-option
          v-for="item in candidates"
          :key="item.item_uid"
          :label="item.name"
          :value="item.item_uid"
        >
          <span>{{ item.name }}</span>
          <el-tag
            v-if="item.item_type === 'artifact' || item.meta?.tribulation_inefficient"
            size="small"
            type="info"
            class="ineff-tag"
          >
            可抵劫，效率极差
          </el-tag>
        </el-option>
      </el-select>
      <el-button size="small" text :disabled="index === 0" @click="moveSlot(index, -1)">
        ↑
      </el-button>
      <el-button
        size="small"
        text
        :disabled="index >= slots.length - 1"
        @click="moveSlot(index, 1)"
      >
        ↓
      </el-button>
    </div>

    <el-form label-position="top" size="small" class="extra">
      <el-form-item label="阵法（可选）">
        <el-input v-model="formationId" placeholder="formation_id" clearable />
      </el-form-item>
      <el-form-item>
        <el-checkbox v-model="veilSelected">准备遮天道具</el-checkbox>
      </el-form-item>
    </el-form>

    <div class="actions">
      <el-button :loading="saving" @click="onSave">保存准备</el-button>
      <el-button type="primary" :loading="saving" @click="onCommit">确认准备</el-button>
    </div>
  </el-card>
</template>

<style scoped>
.consume-alert {
  margin-bottom: 0.75rem;
}

.consume-list {
  margin: 0.35rem 0 0;
  padding-left: 1.1rem;
  font-size: 0.85rem;
  line-height: 1.55;
}

.tip {
  display: block;
  margin-bottom: 0.75rem;
}

.slot-row {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 0.5rem;
}

.slot-select {
  flex: 1;
  min-width: 140px;
}

.ineff-tag {
  margin-left: 0.35rem;
}

.extra {
  margin-top: 0.75rem;
}

.actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
</style>
