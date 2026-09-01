<script setup lang="ts">
/**
 * Technique research workbench: 心法雏形, slot pickers for formal cards, cultivate.
 * Blank/type cards and manuals are used from the bag (洞府储物), not listed here.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PoolPickerGrid from '../character/PoolPickerGrid.vue'
import ResearchMineList from './ResearchMineList.vue'
import { usePlayWriteGate } from '../../composables/usePlayWriteGate'
import { useTechniqueCraftStore } from '../../stores/techniqueCraft'
import { useInventoryStore } from '../../stores/inventory'
import { useCharacterStore } from '../../stores/character'
import type { InventoryItem } from '../../types/inventory'
import type { PoolCandidate } from '../../types/itemHover'
import {
  IDLE_EFFICACIES,
  TECH_CARD_FORMAL_EFFICACY_IDS,
  TECH_CARD_FORMAL_ELEMENT_IDS,
  TECHNIQUE_CRAFT_HELP_ZH,
  WEAPON_LIMIT_OPTIONS,
  affixLabelZh,
  affixSlotLabelZh,
  formatAffixStats,
  asAffixSlots,
  efficacyLabelZh,
  elementLabelZh,
  rankLabelZh,
  weaponLabelZh,
  type TechniqueAffixSlot,
  type TechniqueAffixView,
  type TechniqueDraftPublic,
  type TechniqueMineFields,
} from '../../types/techniqueCraft'
import { shortItemName } from '../../utils/itemHoverFormat'

/** Heavenly stems for unlabeled empty drafts — no arabic serial numbers. */
const STEM_CAPTIONS = [
  '甲篇',
  '乙篇',
  '丙篇',
  '丁篇',
  '戊篇',
  '己篇',
  '庚篇',
  '辛篇',
  '壬篇',
  '癸篇',
] as const

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const craftStore = useTechniqueCraftStore()
const inventoryStore = useInventoryStore()
const characterStore = useCharacterStore()
const { writeBlocked } = usePlayWriteGate()

const busy = ref(false)
const elementLimit = ref('')
const weaponLimit = ref('')
const labelZh = ref('')
/** Which embed slot is open for PoolPickerGrid: element | efficacy | null */
const pickerKind = ref<'element' | 'efficacy' | null>(null)

const draft = computed(() => craftStore.selectedDraft)
const original = computed(() => craftStore.selectedOriginal)

/** List ↔ cultivate detail; upgrade UI only after 「升级功法」. */
const cultivating = ref(false)

const affixSlots = computed(() => asAffixSlots(draft.value?.affixes))
const originalAffixSlots = computed(() => asAffixSlots(original.value?.affixes))

const showMainEquipHint = computed(() => {
  const efficacy = original.value?.efficacy
  if (!efficacy) return false
  return IDLE_EFFICACIES.has(efficacy)
})

const breakthroughHint = computed(() => {
  const row = original.value
  if (!row) return ''
  const need = row.breakthrough_points_required
  const next = row.next_rank
  const nextZh = row.next_rank_label_zh || rankLabelZh(next)
  if (!next || need == null) {
    return `当前 ${row.major_rank_label_zh || rankLabelZh(row.major_rank)}阶已是最高阶`
  }
  const cur = Number(row.upgrade_points || 0)
  if (cur >= need) {
    return `升级点已达 ${cur} / ${need}，可尝试突破至${nextZh}`
  }
  return `突破至${nextZh}需升级点 ${need}（当前 ${cur}，还差 ${need - cur}）`
})

function displayRankZh(
  id: string | null | undefined,
  labelFromApi?: string | null,
): string {
  const fromApi = String(labelFromApi || '').trim()
  if (fromApi) return fromApi
  return rankLabelZh(id)
}

const conditionBonusLines = computed(() => {
  const bonus = original.value?.condition_bonus
  if (!bonus) return [] as string[]
  const lines: string[] = []
  const el = bonus.element_limit
  const wp = bonus.weapon_limit
  lines.push(
    `属性限制：${el ? elementLabelZh(el) : '不选'} · 装备限制：${weaponLabelZh(wp || '')}`,
  )
  const wb = bonus.weapon_bonus || {}
  const wbKeys = Object.keys(wb)
  if (wp && wbKeys.length) {
    lines.push(
      `装备条件加成：${wbKeys.map((k) => `${k} ${wb[k] > 0 ? '+' : ''}${wb[k]}`).join('、')}`,
    )
  } else if (wp) {
    lines.push('装备条件加成：待配置')
  } else {
    lines.push('装备条件加成：未选限制 · 无加成')
  }
  const eb = bonus.element_bonus || {}
  const ebKeys = Object.keys(eb)
  if (el && ebKeys.length) {
    lines.push(
      `属性条件加成：${ebKeys.map((k) => `${k} ${eb[k] > 0 ? '+' : ''}${eb[k]}`).join('、')}`,
    )
  } else {
    lines.push('属性条件加成：栏位预留（后续后台可配）')
  }
  return lines
})

const elementFilled = computed(() => Boolean(draft.value?.elements.length))
const efficacyFilled = computed(() => Boolean(draft.value?.efficacy))

function cardDetail(item: InventoryItem): string {
  const meta = item.meta || {}
  const elements = meta.elements
  if (Array.isArray(elements) && elements.length) {
    return elements.map((x) => elementLabelZh(String(x))).join('、')
  }
  if (typeof meta.efficacy === 'string' && meta.efficacy) {
    return efficacyLabelZh(meta.efficacy)
  }
  return ''
}

function formalCardsOf(kind: 'element' | 'efficacy'): InventoryItem[] {
  const ids = kind === 'element' ? TECH_CARD_FORMAL_ELEMENT_IDS : TECH_CARD_FORMAL_EFFICACY_IDS
  return inventoryStore.items.filter((row) => ids.includes(row.item_id))
}

function draftCaption(row: TechniqueDraftPublic, index: number): string {
  const name = (row.label_zh || '').trim()
  if (name) return name
  const parts: string[] = []
  if (row.elements?.length) {
    parts.push(row.elements.map((el) => elementLabelZh(el)).join(''))
  }
  if (row.efficacy) {
    parts.push(efficacyLabelZh(row.efficacy))
  }
  if (parts.length) return parts.join(' · ')
  return STEM_CAPTIONS[index] ?? '无名篇'
}

const pickerCandidates = computed((): PoolCandidate[] => {
  if (!pickerKind.value || !draft.value) return []
  if (pickerKind.value === 'element' && elementFilled.value) return []
  if (pickerKind.value === 'efficacy' && efficacyFilled.value) return []
  return formalCardsOf(pickerKind.value).map((item) => {
    const detail = cardDetail(item)
    return {
      key: item.item_uid,
      shortName: shortItemName(detail || item.name, 4),
      worn: false,
      hover: {
        name: item.name,
        subtitle: detail || undefined,
        cornerZh:
          pickerKind.value === 'element'
            ? item.item_id.includes('_inf')
              ? '属性·无限'
              : '属性'
            : item.item_id.includes('_inf')
              ? '效能·无限'
              : '效能',
        helpZh: item.item_id.includes('_inf')
          ? '测试卡：点选镶入，不消耗'
          : '点选镶入心法雏形（可失败，失败则卡消耗）',
        elements:
          pickerKind.value === 'element' && Array.isArray(item.meta?.elements)
            ? (item.meta!.elements as string[]).map((el) => ({
                id: String(el),
                label_zh: elementLabelZh(String(el)),
              }))
            : undefined,
        stats:
          pickerKind.value === 'efficacy' && typeof item.meta?.efficacy === 'string'
            ? [{ label_zh: '效能', value: efficacyLabelZh(item.meta.efficacy) }]
            : undefined,
      },
    }
  })
})

const pickerTitle = computed(() => {
  if (pickerKind.value === 'element') return '选择 · 属性正式卡'
  if (pickerKind.value === 'efficacy') return '选择 · 效能正式卡'
  return ''
})

const pickerEmpty = computed(() => {
  if (pickerKind.value === 'element') {
    return elementFilled.value
      ? '属性已镶嵌'
      : '背包暂无属性正式卡，请先在洞府储物开卡'
  }
  if (pickerKind.value === 'efficacy') {
    return efficacyFilled.value
      ? '效能已镶嵌'
      : '背包暂无效能正式卡，请先在洞府储物开卡'
  }
  return ''
})

watch(
  () => draft.value?.id,
  () => {
    const row = draft.value
    pickerKind.value = null
    elementLimit.value = row?.element_limit || ''
    weaponLimit.value = row?.weapon_limit || ''
    labelZh.value = row?.label_zh || ''
  },
)

async function runBusy(work: () => Promise<void>): Promise<void> {
  if (writeBlocked.value) return
  busy.value = true
  try {
    await work()
  } finally {
    busy.value = false
  }
}

function fail(err: string): void {
  ElMessage.error(err)
  emit('log', err, 'warning')
}

async function onNewDraft(): Promise<void> {
  await runBusy(async () => {
    const err = await craftStore.createDraft()
    if (err) {
      fail(err)
      return
    }
    ElMessage.success('已另开新篇')
    emit('log', '已另开心法雏形', 'success')
  })
}

async function onAbandon(): Promise<void> {
  if (writeBlocked.value) return
  if (!draft.value) return
  try {
    await ElMessageBox.confirm('放弃后不退已镶嵌的正式卡。确定放弃？', '放弃雏形', {
      type: 'warning',
      confirmButtonText: '放弃',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await runBusy(async () => {
    const err = await craftStore.abandonDraft()
    if (err) {
      fail(err)
      return
    }
    pickerKind.value = null
    ElMessage.success('已放弃雏形')
    emit('log', '已放弃心法雏形', 'info')
  })
}

function onOpenPicker(kind: 'element' | 'efficacy'): void {
  if (writeBlocked.value) return
  if (!draft.value) return
  if (kind === 'element' && elementFilled.value) {
    ElMessage.info('属性已镶嵌，不可更换')
    return
  }
  if (kind === 'efficacy' && efficacyFilled.value) {
    ElMessage.info('效能已镶嵌，不可更换')
    return
  }
  pickerKind.value = pickerKind.value === kind ? null : kind
}

async function onPickFormal(candidate: PoolCandidate): Promise<void> {
  await runBusy(async () => {
    const result = await craftStore.embed(candidate.key)
    if (result.error) {
      fail(result.error)
      return
    }
    await inventoryStore.load()
    if (result.failed) {
      ElMessage.warning('镶嵌失败，正式卡已消耗')
      emit('log', '镶嵌失败，正式卡已消耗', 'warning')
      return
    }
    pickerKind.value = null
    ElMessage.success('镶嵌成功')
    emit('log', '正式卡镶嵌成功', 'success')
  })
}

async function onConditions(): Promise<void> {
  await runBusy(async () => {
    const err = await craftStore.setConditions(
      elementLimit.value || null,
      weaponLimit.value || null,
    )
    if (err) {
      fail(err)
      return
    }
    ElMessage.success('已确认发动条件')
    emit('log', '已确认发动条件', 'success')
  })
}

async function onRoll(slot: number): Promise<void> {
  await runBusy(async () => {
    const err = await craftStore.rollAffix(slot)
    if (err) {
      fail(err)
      return
    }
    emit('log', `${affixSlotLabelZh(slot)}已生成词条`, 'info')
  })
}

async function onChoose(slot: number, affixId: string): Promise<void> {
  await runBusy(async () => {
    const err = await craftStore.chooseAffix(slot, affixId)
    if (err) {
      fail(err)
      return
    }
    emit('log', `已选择词条「${affixLabelZh(affixId)}」`, 'success')
  })
}

async function onReroll(slot: number): Promise<void> {
  await runBusy(async () => {
    const err = await craftStore.rerollAffix(slot)
    if (err) {
      fail(err)
      return
    }
    emit('log', `${affixSlotLabelZh(slot)}已重随`, 'info')
  })
}

/** Highlight only the first matching option when duplicates exist. */
function isAffixOptionChosen(
  slot: { chosen_id: string | null; options: string[] },
  opt: string,
  optIdx: number,
): boolean {
  if (!slot.chosen_id || slot.chosen_id !== opt) return false
  return slot.options.indexOf(slot.chosen_id) === optIdx
}

function optionViewFor(
  slot: TechniqueAffixSlot,
  opt: string,
  optIdx: number,
): TechniqueAffixView | null {
  const views = slot.option_views || []
  if (views[optIdx] && views[optIdx].id === opt) return views[optIdx]
  return views.find((v) => v.id === opt) || null
}

function optionButtonLabel(slot: TechniqueAffixSlot, opt: string, optIdx: number): string {
  const view = optionViewFor(slot, opt, optIdx)
  if (!view) return affixLabelZh(opt)
  return `[${view.rarity_label_zh}] ${view.label_zh}（${formatAffixStats(view.stats)}）`
}

function optionButtonStyle(
  slot: TechniqueAffixSlot,
  opt: string,
  optIdx: number,
): Record<string, string> {
  const view = optionViewFor(slot, opt, optIdx)
  const color = view?.color || '#909399'
  if (isAffixOptionChosen(slot, opt, optIdx)) {
    return {
      backgroundColor: color,
      borderColor: color,
      color: rarityTextColor(view?.rarity),
    }
  }
  return {
    borderColor: color,
    color,
  }
}

function rarityTextColor(rarity: string | undefined): string {
  if (rarity === 'white' || rarity === 'gray') return '#303133'
  return '#ffffff'
}

async function onFinalize(): Promise<void> {
  if (writeBlocked.value) return
  const name = labelZh.value.trim()
  if (name.length < 2) {
    ElMessage.info('请先填写中文名称（2～16字）')
    return
  }
  try {
    await ElMessageBox.confirm('定稿后属性、效能与发动条件锁定，可继续培养。', '确认定稿', {
      type: 'warning',
      confirmButtonText: '定稿',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await runBusy(async () => {
    const err = await craftStore.finalize(name)
    if (err) {
      fail(err)
      return
    }
    ElMessage.success('定稿成功')
    emit('log', `功法「${name}」已定稿`, 'success')
    labelZh.value = ''
    cultivating.value = false
  })
}

function onPickOriginal(row: TechniqueMineFields): void {
  craftStore.selectOriginalFromMine(row)
  cultivating.value = true
}

function onBackToMineList(): void {
  cultivating.value = false
}

async function onBase(stat: 'attack' | 'defense' | 'speed'): Promise<void> {
  await runBusy(async () => {
    const err = await craftStore.upgradeBase(stat)
    if (err) {
      fail(err)
      return
    }
    const names = { attack: '攻击', defense: '防御', speed: '速度' }
    ElMessage.success(`已升级${names[stat]}`)
    emit('log', `基础加成：${names[stat]}`, 'success')
  })
}

async function onAffixUpgrade(slot: number): Promise<void> {
  await runBusy(async () => {
    const result = await craftStore.upgradeAffix(slot)
    if (result.error) {
      fail(result.error)
      return
    }
    if (result.failed) {
      ElMessage.warning('词条升级失败，资源已扣除')
      emit('log', '词条升级失败，资源已扣除', 'warning')
      return
    }
    ElMessage.success('词条升级成功')
    emit('log', '词条升级成功', 'success')
  })
}

async function onBreakthrough(): Promise<void> {
  await runBusy(async () => {
    const result = await craftStore.breakthrough()
    if (result.error) {
      fail(result.error)
      return
    }
    if (result.failed) {
      ElMessage.warning('突破失败，资源已扣除，升级点与当前阶不变')
      emit('log', '功法突破失败', 'warning')
      return
    }
    ElMessage.success(
      `已突破至${displayRankZh(original.value?.major_rank, original.value?.major_rank_label_zh)}`,
    )
    emit(
      'log',
      `功法突破至${displayRankZh(original.value?.major_rank, original.value?.major_rank_label_zh)}`,
      'success',
    )
  })
}

async function onPrintManual(): Promise<void> {
  await runBusy(async () => {
    const err = await craftStore.printManual()
    if (err) {
      fail(err)
      return
    }
    ElMessage.success('已制成秘籍')
    emit('log', '已制成秘籍', 'success')
  })
}

async function onAbolish(): Promise<void> {
  const name = original.value?.label_zh || '该功法'
  try {
    await ElMessageBox.confirm(
      `废除后你将失去「${name}」，已制成的秘籍、他人学会的副本与藏经阁/弟子传承不受影响。须先卸下装备中的该功法。确定废除？`,
      '废除功法',
      {
        type: 'warning',
        confirmButtonText: '废除',
        cancelButtonText: '取消',
      },
    )
  } catch {
    return
  }
  await runBusy(async () => {
    const err = await craftStore.abolish()
    if (err) {
      fail(err)
      return
    }
    ElMessage.success('已废除功法')
    emit('log', `已废除「${name}」`, 'warning')
    cultivating.value = false
  })
}

onMounted(() => {
  void inventoryStore.load()
  void craftStore.loadDrafts()
})
</script>

<template>
  <div class="tech-bench">
    <section class="bench-left">
      <el-card shadow="never" class="bench-card">
        <template #header>
          <div class="card-head">
            <el-text tag="b" size="small">心法雏形</el-text>
            <el-button
              type="primary"
              size="small"
              :loading="busy"
              :disabled="writeBlocked"
              @click="onNewDraft"
            >
              另开新篇
            </el-button>
          </div>
        </template>
        <el-text size="small" type="info" class="help">{{ TECHNIQUE_CRAFT_HELP_ZH }}</el-text>
        <div v-if="craftStore.drafts.length" class="chip-row">
          <button
            v-for="(row, index) in craftStore.drafts"
            :key="row.id"
            type="button"
            class="draft-chip"
            :class="{ active: craftStore.selectedDraftId === row.id }"
            @click="craftStore.selectDraft(row.id)"
          >
            {{ draftCaption(row, index) }}
          </button>
        </div>
        <el-empty
          v-else
          description="尚无雏形，点「另开新篇」开始"
          :image-size="48"
        />
      </el-card>

      <el-card v-if="draft" shadow="never" class="bench-card">
        <template #header>
          <div class="card-head">
            <el-text tag="b" size="small">{{
              draftCaption(
                draft,
                Math.max(
                  0,
                  craftStore.drafts.findIndex((d) => d.id === draft!.id),
                ),
              )
            }}</el-text>
            <el-button
              link
              type="danger"
              size="small"
              :disabled="writeBlocked || busy"
              @click="onAbandon"
            >
              放弃
            </el-button>
          </div>
        </template>

        <div class="embed-board">
          <el-text size="small" class="section-label">镶嵌</el-text>
          <div class="embed-cells">
            <button
              type="button"
              class="embed-cell"
              :class="{
                filled: elementFilled,
                selected: pickerKind === 'element',
              }"
              :disabled="writeBlocked"
              @click="onOpenPicker('element')"
            >
              <span class="embed-label">属性</span>
              <span class="embed-value">
                <template v-if="elementFilled">
                  {{ draft.elements.map((el) => elementLabelZh(el)).join('、') }}
                </template>
                <template v-else>点选镶入</template>
              </span>
            </button>
            <button
              type="button"
              class="embed-cell"
              :class="{
                filled: efficacyFilled,
                selected: pickerKind === 'efficacy',
              }"
              :disabled="writeBlocked"
              @click="onOpenPicker('efficacy')"
            >
              <span class="embed-label">效能</span>
              <span class="embed-value">
                {{ efficacyFilled ? efficacyLabelZh(draft.efficacy) : '点选镶入' }}
              </span>
            </button>
          </div>
          <PoolPickerGrid
            v-if="pickerKind"
            :title="pickerTitle"
            :empty-text="pickerEmpty"
            :items="pickerCandidates"
            :busy="busy"
            @pick="onPickFormal"
          />
        </div>

        <el-divider content-position="left">发动条件</el-divider>
        <el-form label-width="5.5rem" size="small" class="cond-form">
          <el-form-item label="属性限制">
            <el-select
              v-model="elementLimit"
              size="small"
              class="select"
              :disabled="writeBlocked || !elementFilled"
            >
              <el-option label="不选" value="" />
              <el-option
                v-for="el in draft.elements"
                :key="el"
                :label="elementLabelZh(el)"
                :value="el"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="装备限制">
            <el-select
              v-model="weaponLimit"
              size="small"
              class="select"
              :disabled="writeBlocked || !efficacyFilled"
            >
              <el-option label="不选" value="" />
              <el-option
                v-for="opt in WEAPON_LIMIT_OPTIONS"
                :key="opt.id"
                :label="opt.label_zh"
                :value="opt.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button
              size="small"
              :loading="busy"
              :disabled="writeBlocked || !elementFilled || !efficacyFilled"
              @click="onConditions"
            >
              确认发动条件
            </el-button>
          </el-form-item>
        </el-form>

        <el-divider content-position="left">词条</el-divider>
        <div
          v-for="(slot, index) in affixSlots"
          :key="index"
          class="affix-block"
        >
          <el-text size="small" tag="b">{{ affixSlotLabelZh(index) }}</el-text>
          <el-button
            v-if="!slot.options.length"
            size="small"
            :loading="busy"
            :disabled="writeBlocked || !efficacyFilled"
            @click="onRoll(index)"
          >
            生成三选
          </el-button>
          <template v-else>
            <div class="chip-row affix-options">
              <el-button
                v-for="(opt, optIdx) in slot.options"
                :key="`${index}-${optIdx}-${opt}`"
                size="small"
                :type="isAffixOptionChosen(slot, opt, optIdx) ? 'primary' : 'default'"
                :style="optionButtonStyle(slot, opt, optIdx)"
                :disabled="writeBlocked"
                @click="onChoose(index, opt)"
              >
                {{ optionButtonLabel(slot, opt, optIdx) }}
              </el-button>
            </div>
            <el-text v-if="slot.chosen_id" size="small" type="success">
              已选
              {{
                slot.chosen_view
                  ? `[${slot.chosen_view.rarity_label_zh}] ${slot.chosen_view.label_zh}（${formatAffixStats(slot.chosen_view.stats)}）`
                  : affixLabelZh(slot.chosen_id)
              }}
            </el-text>
            <el-button
              size="small"
              :loading="busy"
              :disabled="writeBlocked"
              @click="onReroll(index)"
            >
              重随
            </el-button>
          </template>
        </div>

        <el-divider content-position="left">定稿</el-divider>
        <div class="finalize-row">
          <el-input
            v-model="labelZh"
            size="small"
            maxlength="16"
            show-word-limit
            placeholder="功法名称（2～16字）"
            class="name-input"
            :disabled="writeBlocked"
          />
          <el-button
            type="primary"
            size="small"
            :loading="busy"
            :disabled="writeBlocked || !draft.can_finalize"
            @click="onFinalize"
          >
            定稿
          </el-button>
        </div>
      </el-card>
    </section>

    <section class="bench-right">
      <ResearchMineList
        v-if="!cultivating"
        kind="technique"
        @cultivate-technique="onPickOriginal"
      />

      <el-card v-else shadow="never" class="bench-card cultivate-card">
        <template #header>
          <div class="card-head">
            <div>
              <el-text tag="b" size="small">升级功法</el-text>
              <el-text v-if="original" size="small" type="info" class="cultivate-sub">
                {{ original.label_zh }}
              </el-text>
            </div>
            <el-button size="small" @click="onBackToMineList">返回列表</el-button>
          </div>
        </template>
        <el-empty
          v-if="!original"
          description="请从「我的功法」选择一门再升级"
          :image-size="48"
        />
        <template v-else>
            <el-text size="small" class="help">
              {{ original.label_zh }} · {{ efficacyLabelZh(original.efficacy) }} ·
              {{ displayRankZh(original.major_rank, original.major_rank_label_zh) }}阶
            </el-text>
            <el-text size="small" class="help">
              <template
                v-if="
                  original.next_rank && original.breakthrough_points_required != null
                "
              >
                升级点 {{ original.upgrade_points }} /
                {{ original.breakthrough_points_required }}
                （下一阶{{
                  displayRankZh(original.next_rank, original.next_rank_label_zh)
                }}）
              </template>
              <template v-else> 升级点 {{ original.upgrade_points }} · 已达最高阶 </template>
            </el-text>
            <el-text size="small" type="warning" class="help">
              {{ breakthroughHint }}
            </el-text>
            <el-text size="small" type="info" class="help">
              修为 {{ characterStore.character?.cultivation_points ?? 0 }} /
              炼体 {{ characterStore.character?.body_tempering_points ?? 0 }}
            </el-text>
            <el-text v-if="showMainEquipHint" size="small" type="info" class="help">
              可装备为主功法或技法（装备时二选一）
            </el-text>

            <el-divider content-position="left">基础属性（皆可升级）</el-divider>
            <div class="chip-row">
              <el-button
                size="small"
                :loading="busy"
                :disabled="writeBlocked"
                @click="onBase('attack')"
              >
                升级攻击（{{ original.base.attack || 0 }}）
              </el-button>
              <el-button
                size="small"
                :loading="busy"
                :disabled="writeBlocked"
                @click="onBase('defense')"
              >
                升级防御（{{ original.base.defense || 0 }}）
              </el-button>
              <el-button
                size="small"
                :loading="busy"
                :disabled="writeBlocked"
                @click="onBase('speed')"
              >
                升级速度（{{ original.base.speed || 0 }}）
              </el-button>
            </div>

            <el-divider content-position="left">词条（皆可升级）</el-divider>
            <div class="chip-row">
              <el-button
                v-for="(slot, index) in originalAffixSlots"
                :key="`up-${index}`"
                size="small"
                :loading="busy"
                :disabled="writeBlocked || !slot.chosen_id"
                :style="
                  slot.chosen_view
                    ? {
                        borderColor: slot.chosen_view.color,
                        color: slot.chosen_view.color,
                      }
                    : undefined
                "
                @click="onAffixUpgrade(index)"
              >
                升级 ·
                {{
                  slot.chosen_view
                    ? `[${slot.chosen_view.rarity_label_zh}] ${slot.chosen_view.label_zh}`
                    : affixLabelZh(slot.chosen_id)
                }}
                Lv.{{ slot.chosen_level }}
                <template v-if="slot.next_upgrade_cost != null">
                  （耗 {{ slot.next_upgrade_cost }}）
                </template>
              </el-button>
            </div>
            <el-text
              v-for="(slot, index) in originalAffixSlots"
              :key="`st-${index}`"
              size="small"
              class="help"
            >
              {{ affixSlotLabelZh(index) }}：
              {{
                slot.chosen_view
                  ? formatAffixStats(slot.chosen_view.stats)
                  : '未选'
              }}
            </el-text>

            <el-divider content-position="left">发动条件加成（预留）</el-divider>
            <el-text
              v-for="(line, idx) in conditionBonusLines"
              :key="`cb-${idx}`"
              size="small"
              class="help"
            >
              {{ line }}
            </el-text>
            <el-text size="small" type="info" class="help">
              {{
                original.condition_bonus?.help_zh ||
                '可用词条 / 条件加成 / 可用属性后续由运营后台配置。'
              }}
            </el-text>

            <el-divider content-position="left">突破与流通</el-divider>
            <div class="chip-row">
              <el-button
                type="warning"
                size="small"
                :loading="busy"
                :disabled="writeBlocked"
                @click="onBreakthrough"
              >
                突破
                <template
                  v-if="
                    original.next_rank && original.breakthrough_points_required != null
                  "
                >
                  （至{{
                    displayRankZh(original.next_rank, original.next_rank_label_zh)
                  }}需
                  {{ original.breakthrough_points_required }} 点）
                </template>
                <template v-else> （已达最高阶） </template>
              </el-button>
              <el-button
                size="small"
                :loading="busy"
                :disabled="writeBlocked"
                @click="onPrintManual"
              >
                制成秘籍
              </el-button>
              <el-button
                type="danger"
                plain
                size="small"
                :loading="busy"
                :disabled="writeBlocked"
                @click="onAbolish"
              >
                废除
              </el-button>
            </div>
            <el-text size="small" type="info" class="help">
              定稿起于锻体，须逐步突破；废除前请卸装，只删你自己的本门，流通副本仍在。
            </el-text>
        </template>
      </el-card>
    </section>
  </div>
</template>

<style scoped>
.tech-bench {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  gap: 0.75rem;
  align-items: start;
}
.bench-left,
.bench-right {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-width: 0;
}
.bench-card {
  width: 100%;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.cultivate-sub {
  display: block;
  margin-top: 0.15rem;
}
.cultivate-card {
  border: 1px solid color-mix(in srgb, var(--el-color-warning) 28%, var(--el-border-color-lighter));
  background: linear-gradient(
    165deg,
    color-mix(in srgb, var(--el-color-warning) 6%, transparent),
    transparent 40%
  );
}
.help {
  display: block;
  margin-bottom: 0.65rem;
  line-height: 1.45;
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.45rem;
}
.draft-chip {
  min-width: 4.5rem;
  padding: 0.35rem 0.55rem;
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.draft-chip.active {
  border-style: solid;
  border-color: #c9930f;
  box-shadow: 0 0 0 2px #c9930f;
}
.section-label {
  display: block;
  text-align: center;
  margin-bottom: 0.35rem;
  color: var(--el-text-color-regular);
}
.embed-board {
  margin-bottom: 0.35rem;
}
.embed-cells {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.5rem;
}
.embed-cell {
  width: 7.5rem;
  min-height: 4.25rem;
  padding: 0.45rem 0.4rem;
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
}
.embed-cell:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}
.embed-cell.filled {
  border-style: solid;
}
.embed-cell.selected {
  box-shadow: 0 0 0 2px #c9930f;
}
.embed-label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.embed-value {
  font-size: 13px;
  line-height: 1.2;
  text-align: center;
  color: var(--el-text-color-regular);
}
.cond-form {
  max-width: 22rem;
}
.select {
  max-width: 14rem;
  width: 100%;
}
.affix-block {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin-bottom: 0.65rem;
}
.finalize-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem;
}
.name-input {
  max-width: 14rem;
}
@media (max-width: 900px) {
  .tech-bench {
    grid-template-columns: 1fr;
  }
}
</style>
