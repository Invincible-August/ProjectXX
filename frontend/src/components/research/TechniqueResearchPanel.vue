<script setup lang="ts">
/**
 * Technique research workbench: card drafts, embed, conditions, affix, cultivate.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { usePlayWriteGate } from '../../composables/usePlayWriteGate'
import { useTechniqueCraftStore } from '../../stores/techniqueCraft'
import { useInventoryStore } from '../../stores/inventory'
import { useResearchStore } from '../../stores/research'
import { useCharacterStore } from '../../stores/character'
import type { InventoryItem } from '../../types/inventory'
import {
  IDLE_EFFICACIES,
  TECH_CARD_ALL_IDS,
  TECH_CARD_FORMAL_IDS,
  TECH_CARD_USEABLE_IDS,
  TECHNIQUE_CRAFT_HELP_ZH,
  WEAPON_LIMIT_OPTIONS,
  affixLabelZh,
  asAffixSlots,
  efficacyLabelZh,
  elementLabelZh,
  rankLabelZh,
  type TechniqueMineFields,
} from '../../types/techniqueCraft'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const craftStore = useTechniqueCraftStore()
const inventoryStore = useInventoryStore()
const researchStore = useResearchStore()
const characterStore = useCharacterStore()
const { writeBlocked } = usePlayWriteGate()

const busy = ref(false)
const embedUid = ref('')
const elementLimit = ref('')
const weaponLimit = ref('')
const labelZh = ref('')

const draft = computed(() => craftStore.selectedDraft)
const original = computed(() => craftStore.selectedOriginal)

const craftCards = computed(() =>
  inventoryStore.items.filter((row) => TECH_CARD_ALL_IDS.includes(row.item_id)),
)

const formalCards = computed(() => {
  const rows = inventoryStore.items.filter((row) => TECH_CARD_FORMAL_IDS.includes(row.item_id))
  if (!draft.value) return rows
  return rows.filter((row) => {
    if (row.item_id === 'tech_card_formal_element') return draft.value!.elements.length === 0
    if (row.item_id === 'tech_card_formal_efficacy') return !draft.value!.efficacy
    return true
  })
})

const originals = computed(() =>
  researchStore.mine
    .filter((row) => row.kind === 'technique')
    .map((row) => row as unknown as TechniqueMineFields)
    .filter((row) => row.cultivable !== false),
)

const affixSlots = computed(() => asAffixSlots(draft.value?.affixes))
const originalAffixSlots = computed(() => asAffixSlots(original.value?.affixes))

const showMainEquipHint = computed(() => {
  const efficacy = original.value?.efficacy
  if (!efficacy) return false
  return IDLE_EFFICACIES.has(efficacy)
})

watch(
  () => draft.value?.id,
  () => {
    const row = draft.value
    embedUid.value = ''
    elementLimit.value = row?.element_limit || ''
    weaponLimit.value = row?.weapon_limit || ''
    labelZh.value = row?.label_zh || ''
  },
)

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

function canUseCard(item: InventoryItem): boolean {
  return TECH_CARD_USEABLE_IDS.includes(item.item_id)
}

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
    ElMessage.success('已新建草稿')
    emit('log', '已新建功法草稿', 'success')
  })
}

async function onAbandon(): Promise<void> {
  if (writeBlocked.value) return
  if (!draft.value) return
  try {
    await ElMessageBox.confirm('放弃后不退已镶嵌的正式卡。确定放弃？', '放弃草稿', {
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
    ElMessage.success('已放弃草稿')
    emit('log', '已放弃功法草稿', 'info')
  })
}

async function onUseCard(item: InventoryItem): Promise<void> {
  await runBusy(async () => {
    const err = await inventoryStore.use(item.item_uid)
    if (err) {
      fail(err)
      return
    }
    ElMessage.success(`已使用${item.name}`)
    emit('log', `已使用${item.name}`, 'success')
  })
}

async function onEmbed(): Promise<void> {
  if (!embedUid.value) {
    ElMessage.info('请选择一张正式卡')
    return
  }
  await runBusy(async () => {
    const result = await craftStore.embed(embedUid.value)
    if (result.error) {
      fail(result.error)
      return
    }
    embedUid.value = ''
    await inventoryStore.load()
    if (result.failed) {
      ElMessage.warning('镶嵌失败，正式卡已消耗')
      emit('log', '镶嵌失败，正式卡已消耗', 'warning')
      return
    }
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
    emit('log', `第${slot + 1}栏已生成词条`, 'info')
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
    emit('log', `第${slot + 1}栏已重随`, 'info')
  })
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
  })
}

function onPickOriginal(row: TechniqueMineFields): void {
  craftStore.selectOriginalFromMine(row)
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
    ElMessage.success(`已突破至${rankLabelZh(original.value?.major_rank)}`)
    emit('log', `功法突破至${rankLabelZh(original.value?.major_rank)}`, 'success')
  })
}

onMounted(() => {
  void inventoryStore.load()
  void craftStore.loadDrafts()
})
</script>

<template>
  <div class="tech-research">
    <el-card shadow="never">
      <template #header>
        <el-text tag="b" size="small">功法草稿</el-text>
      </template>
      <el-text size="small" type="info" class="help">{{ TECHNIQUE_CRAFT_HELP_ZH }}</el-text>
      <div class="actions">
        <el-button
          v-for="row in craftStore.drafts"
          :key="row.id"
          size="small"
          :type="craftStore.selectedDraftId === row.id ? 'primary' : 'default'"
          @click="craftStore.selectDraft(row.id)"
        >
          {{ row.label_zh || `草稿 #${row.id}` }}
        </el-button>
        <el-button
          type="primary"
          size="small"
          :loading="busy"
          :disabled="writeBlocked"
          @click="onNewDraft"
        >
          新建草稿
        </el-button>
      </div>
      <el-empty
        v-if="!craftStore.drafts.length"
        description="尚无草稿，点「新建草稿」开始"
        :image-size="48"
      />
    </el-card>

    <el-card shadow="never">
      <template #header>
        <el-text tag="b" size="small">背包卡片</el-text>
      </template>
      <el-empty
        v-if="!craftCards.length"
        description="背包暂无空白卡 / 类型卡 / 正式卡"
        :image-size="48"
      />
      <div v-else class="card-list">
        <div v-for="item in craftCards" :key="item.item_uid" class="card-row">
          <el-text size="small">{{ item.name }} ×{{ item.quantity }}</el-text>
          <el-tag v-if="cardDetail(item)" size="small">{{ cardDetail(item) }}</el-tag>
          <el-button
            v-if="canUseCard(item)"
            type="primary"
            size="small"
            :loading="busy"
            :disabled="writeBlocked"
            @click="onUseCard(item)"
          >
            使用
          </el-button>
        </div>
      </div>
    </el-card>

    <el-card v-if="draft" shadow="never">
      <template #header>
        <el-text tag="b" size="small">当前草稿 #{{ draft.id }}</el-text>
      </template>
      <el-form label-width="6rem" size="small">
        <el-form-item label="已嵌属性">
          <el-text v-if="!draft.elements.length" size="small" type="info">未镶嵌</el-text>
          <el-tag v-for="el in draft.elements" :key="el" size="small">{{ elementLabelZh(el) }}</el-tag>
        </el-form-item>
        <el-form-item label="已嵌效能">
          <el-text size="small">{{ efficacyLabelZh(draft.efficacy) }}</el-text>
        </el-form-item>
        <el-form-item label="镶嵌正式卡">
          <div class="inline">
            <el-select
              v-model="embedUid"
              size="small"
              clearable
              placeholder="选择正式卡"
              class="select"
              :disabled="writeBlocked || !formalCards.length"
            >
              <el-option
                v-for="item in formalCards"
                :key="item.item_uid"
                :label="`${item.name}${cardDetail(item) ? ' · ' + cardDetail(item) : ''}`"
                :value="item.item_uid"
              />
            </el-select>
            <el-button
              type="primary"
              size="small"
              :loading="busy"
              :disabled="writeBlocked || !embedUid"
              @click="onEmbed"
            >
              镶嵌
            </el-button>
          </div>
        </el-form-item>
        <el-form-item label="属性限制">
          <el-select
            v-model="elementLimit"
            size="small"
            class="select"
            :disabled="writeBlocked || !draft.elements.length"
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
            :disabled="writeBlocked || !draft.efficacy"
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
            :disabled="writeBlocked || !draft.elements.length || !draft.efficacy"
            @click="onConditions"
          >
            确认发动条件
          </el-button>
        </el-form-item>
        <el-form-item
          v-for="(slot, index) in affixSlots"
          :key="index"
          :label="`词条栏 ${index + 1}`"
        >
          <div class="affix-col">
            <el-button
              v-if="!slot.options.length"
              size="small"
              :loading="busy"
              :disabled="writeBlocked || !draft.efficacy"
              @click="onRoll(index)"
            >
              生成三选
            </el-button>
            <template v-else>
              <div class="actions">
                <el-button
                  v-for="(opt, optIdx) in slot.options"
                  :key="`${index}-${optIdx}-${opt}`"
                  size="small"
                  :type="slot.chosen_id === opt ? 'primary' : 'default'"
                  :disabled="writeBlocked"
                  @click="onChoose(index, opt)"
                >
                  {{ affixLabelZh(opt) }}
                </el-button>
              </div>
              <el-text v-if="slot.chosen_id" size="small" type="success">
                已选 {{ affixLabelZh(slot.chosen_id) }}
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
        </el-form-item>
        <el-form-item label="定稿名称">
          <el-input
            v-model="labelZh"
            size="small"
            maxlength="16"
            show-word-limit
            placeholder="2～16字"
            class="name-input"
            :disabled="writeBlocked"
          />
        </el-form-item>
        <el-form-item>
          <div class="actions">
            <el-button
              type="primary"
              size="small"
              :loading="busy"
              :disabled="writeBlocked || !draft.can_finalize"
              @click="onFinalize"
            >
              定稿
            </el-button>
            <el-button size="small" :disabled="writeBlocked || busy" @click="onAbandon">
              放弃草稿
            </el-button>
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <el-text tag="b" size="small">已定稿原创</el-text>
      </template>
      <el-empty
        v-if="!originals.length"
        description="尚无原创功法，定稿后可在此培养"
        :image-size="48"
      />
      <template v-else>
        <div class="actions">
          <el-button
            v-for="row in originals"
            :key="row.id"
            size="small"
            :type="original?.technique_id === row.id ? 'primary' : 'default'"
            @click="onPickOriginal(row)"
          >
            {{ row.label_zh }}
          </el-button>
        </div>
        <template v-if="original">
          <el-text size="small" class="help">
            {{ original.label_zh }} · {{ efficacyLabelZh(original.efficacy) }} ·
            {{ rankLabelZh(original.major_rank) }}阶 · 升级点 {{ original.upgrade_points }}
            （修为 {{ characterStore.character?.cultivation_points ?? 0 }} /
            炼体 {{ characterStore.character?.body_tempering_points ?? 0 }}）
          </el-text>
          <el-text v-if="showMainEquipHint" size="small" type="info" class="help">
            可装备为主功法或技法（装备时二选一）
          </el-text>
          <div class="actions">
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
          <div class="actions">
            <el-button
              v-for="(slot, index) in originalAffixSlots"
              :key="`up-${index}`"
              size="small"
              :loading="busy"
              :disabled="writeBlocked || !slot.chosen_id"
              @click="onAffixUpgrade(index)"
            >
              词条升级 · {{ affixLabelZh(slot.chosen_id) }} Lv.{{ slot.chosen_level }}
            </el-button>
            <el-button
              type="warning"
              size="small"
              :loading="busy"
              :disabled="writeBlocked"
              @click="onBreakthrough"
            >
              突破
            </el-button>
          </div>
        </template>
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
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.5rem;
}
.card-list,
.affix-col {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.card-row,
.inline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
}
.select {
  max-width: 16rem;
}
.name-input {
  max-width: 16rem;
}
</style>
