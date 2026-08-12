<script setup lang="ts">
/**
 * 轮回新生选角：保留道号；选灵根 / 传承 / 体质倾向；可打开商店。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  completeNewborn,
  fetchNewbornOptions,
} from '../../api/reincarnation'
import type { NewbornOptions } from '../../types/reincarnation'
import { useCharacterStore } from '../../stores/character'
import ReincarnationShopPanel from './ReincarnationShopPanel.vue'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
  completed: []
}>()

const characterStore = useCharacterStore()
const options = ref<NewbornOptions | null>(null)
const loading = ref(false)
const busy = ref(false)
const loadError = ref('')
const showShop = ref(false)

const selectedRoots = ref<string[]>([])
const selectedLegacy = ref<string[]>([])
const selectedPath = ref<string>('')

const name = computed(
  () => options.value?.name || characterStore.character?.name || '—',
)
const points = computed(
  () =>
    options.value?.reincarnation_points ??
    characterStore.character?.reincarnation_points ??
    0,
)
const rootSlots = computed(() => options.value?.spirit_root_slots ?? 1)
const legacySlots = computed(() => options.value?.free_legacy_slots ?? 1)

async function reload(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    const envelope = await fetchNewbornOptions()
    if (envelope.code !== 0 || !envelope.data) {
      loadError.value = envelope.message || '加载新生选项失败'
      options.value = null
      return
    }
    options.value = envelope.data
    // 恢复草稿（若曾部分写入）
    selectedRoots.value = [...(envelope.data.current.spirit_root_tags || [])]
    const ownedLegacy = new Set(envelope.data.current.legacy_items || [])
    selectedLegacy.value = (envelope.data.current.legacy_items || []).filter((id) =>
      ownedLegacy.has(id),
    )
    // 免费槽：默认空选，商店已购的仍显示在下方提示
    selectedLegacy.value = []
    selectedPath.value = envelope.data.current.constitution_path || ''
  } catch (e: unknown) {
    loadError.value = e instanceof Error ? e.message : '加载新生选项失败'
  } finally {
    loading.value = false
  }
}

function toggleRoot(id: string): void {
  const idx = selectedRoots.value.indexOf(id)
  if (idx >= 0) {
    selectedRoots.value = selectedRoots.value.filter((x) => x !== id)
    return
  }
  if (selectedRoots.value.length >= rootSlots.value) {
    ElMessage.warning(`灵根最多选 ${rootSlots.value} 个（可在商店购额外位）`)
    return
  }
  selectedRoots.value = [...selectedRoots.value, id]
}

function toggleLegacy(id: string): void {
  const owned = new Set(options.value?.current.legacy_items || [])
  if (owned.has(id)) {
    ElMessage.info('该传承已由商店购入，确认时会自动保留')
    return
  }
  const idx = selectedLegacy.value.indexOf(id)
  if (idx >= 0) {
    selectedLegacy.value = selectedLegacy.value.filter((x) => x !== id)
    return
  }
  if (selectedLegacy.value.length >= legacySlots.value) {
    ElMessage.warning(`免费传承最多选 ${legacySlots.value} 个`)
    return
  }
  selectedLegacy.value = [...selectedLegacy.value, id]
}

async function onConfirm(): Promise<void> {
  if (busy.value || !options.value) return
  if (options.value.require_spirit_root && selectedRoots.value.length === 0) {
    ElMessage.warning('请至少选择一个灵根')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认以道号「${name.value}」开启本世？\n灵根：${selectedRoots.value.join('、') || '无'}\n传承：${selectedLegacy.value.join('、') || '无（商店已购另计）'}`,
      '确认新生',
      { type: 'warning', confirmButtonText: '开启本世', cancelButtonText: '再选选' },
    )
  } catch {
    return
  }
  busy.value = true
  try {
    const envelope = await completeNewborn({
      spirit_root_ids: selectedRoots.value,
      legacy_ids: selectedLegacy.value,
      constitution_path: selectedPath.value || null,
    })
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || '确认新生失败')
    }
    if (envelope.data.character) {
      characterStore.applyCharacter(envelope.data.character)
    } else {
      await characterStore.fetchMe()
    }
    ElMessage.success(envelope.data.message || '新生完成')
    emit('log', envelope.data.message || '新生完成', 'success')
    emit('completed')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '确认新生失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function onShopBought(): Promise<void> {
  await characterStore.fetchMe()
  await reload()
}

onMounted(() => {
  void reload()
})

watch(
  () => characterStore.character?.status,
  (s) => {
    if (s === 'reincarnating') void reload()
  },
)
</script>

<template>
  <div class="newborn-panel">
    <el-alert
      title="轮回新生：道号保留；请选择灵根、传承与体质倾向。确认前可逛轮回商店。"
      type="info"
      show-icon
      :closable="false"
    />

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="true"
      @close="loadError = ''"
    />

    <el-card v-loading="loading" shadow="never">
      <template #header>
        <div class="card-head">
          <el-text tag="b">新生选角</el-text>
          <el-tag size="small" type="warning">周目 {{ options?.reincarnation_count ?? '—' }}</el-tag>
          <el-tag size="small">轮回点 {{ points }}</el-tag>
          <el-button size="small" type="primary" plain @click="showShop = !showShop">
            {{ showShop ? '收起商店' : '轮回商店' }}
          </el-button>
        </div>
      </template>

      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="道号（保留）">
          <el-text tag="b">{{ name }}</el-text>
        </el-descriptions-item>
        <el-descriptions-item label="灵根位">
          已选 {{ selectedRoots.length }} / {{ rootSlots }}
          <el-text v-if="(options?.extra_spirit_root_slots ?? 0) > 0" type="success" size="small">
            （含商店额外 +{{ options?.extra_spirit_root_slots }}）
          </el-text>
        </el-descriptions-item>
        <el-descriptions-item v-if="options?.constitution_slots != null" label="体质槽上限">
          {{ options.constitution_slots }}
          （超额镶嵌已在轮回时自动卸下）
        </el-descriptions-item>
        <el-descriptions-item v-if="options?.permanent_bonus" label="永久加成">
          初始 {{ ((options.permanent_bonus.initial_attr_bonus || 0) * 100).toFixed(1) }}%
          · 小破 {{ ((options.permanent_bonus.minor_growth_bonus || 0) * 100).toFixed(1) }}%
          · 大破 {{ ((options.permanent_bonus.major_growth_bonus || 0) * 100).toFixed(1) }}%
          · 突破率 +{{ ((options.permanent_bonus.break_rate_bonus || 0) * 100).toFixed(1) }}%
        </el-descriptions-item>
        <el-descriptions-item
          v-if="options?.reincarnation_bag_slots != null"
          label="轮回袋容量"
        >
          {{ options.reincarnation_bag_slots }}
        </el-descriptions-item>
      </el-descriptions>

      <section class="section">
        <el-text tag="b">灵根</el-text>
        <div class="option-grid">
          <el-check-tag
            v-for="opt in options?.spirit_roots || []"
            :key="opt.id"
            :checked="selectedRoots.includes(opt.id)"
            @change="toggleRoot(opt.id)"
          >
            <div class="opt-label">{{ opt.label }}</div>
            <div class="opt-summary">{{ opt.summary }}</div>
          </el-check-tag>
        </div>
      </section>

      <section class="section">
        <el-text tag="b">传承（免费 {{ legacySlots }} 槽）</el-text>
        <el-text
          v-if="(options?.current.legacy_items || []).length"
          type="info"
          size="small"
          class="owned-note"
        >
          商店已购：{{ options?.current.legacy_items.join('、') }}（确认时自动保留）
        </el-text>
        <div class="option-grid">
          <el-check-tag
            v-for="opt in options?.legacy_catalog || []"
            :key="opt.id"
            :checked="
              selectedLegacy.includes(opt.id) ||
              (options?.current.legacy_items || []).includes(opt.id)
            "
            @change="toggleLegacy(opt.id)"
          >
            <div class="opt-label">{{ opt.label }}</div>
            <div class="opt-summary">{{ opt.summary }}</div>
          </el-check-tag>
        </div>
      </section>

      <section class="section">
        <el-text tag="b">体质倾向</el-text>
        <el-radio-group v-model="selectedPath" class="path-group">
          <el-radio
            v-for="opt in options?.constitution_paths || []"
            :key="opt.id"
            :value="opt.id"
            border
          >
            <span class="opt-label">{{ opt.label }}</span>
            <span class="opt-summary"> — {{ opt.summary }}</span>
          </el-radio>
        </el-radio-group>
        <el-button
          v-if="selectedPath"
          size="small"
          text
          type="info"
          @click="selectedPath = ''"
        >
          清除倾向
        </el-button>
      </section>

      <section class="section">
        <el-text tag="b">继承体质词条（只读）</el-text>
        <el-empty
          v-if="!(options?.kept_constitutions || []).length"
          description="本世暂无保留体质词条"
          :image-size="48"
        />
        <ul v-else class="kept-list">
          <li v-for="item in options?.kept_constitutions" :key="String(item.id ?? item.def_id)">
            {{ item.name || item.def_id }}
            <el-tag v-if="item.equipped" size="small" type="success">已镶嵌</el-tag>
            <el-tag v-else size="small" type="info">背包</el-tag>
          </li>
        </ul>
      </section>

      <el-button
        type="primary"
        class="confirm-btn"
        :loading="busy"
        :disabled="loading || !!loadError"
        @click="onConfirm"
      >
        确认新生，开启本世
      </el-button>
    </el-card>

    <ReincarnationShopPanel
      v-if="showShop"
      @log="(m, l) => emit('log', m, l)"
      @bought="onShopBought"
    />
  </div>
</template>

<style scoped>
.newborn-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.card-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.section {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.option-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 0.5rem;
}

.opt-label {
  font-weight: 600;
}

.opt-summary {
  font-size: 12px;
  opacity: 0.75;
  margin-top: 0.15rem;
  white-space: normal;
}

.path-group {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.5rem;
}

.kept-list {
  margin: 0;
  padding-left: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.owned-note {
  display: block;
}

.confirm-btn {
  width: 100%;
  margin-top: 1rem;
}
</style>
