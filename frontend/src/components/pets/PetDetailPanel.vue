<script setup lang="ts">
/**
 * 灵宠详情：升级/升阶/词条洗炼/技能装备与领悟（PET-D01/D02）。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { usePetsStore } from '../../stores/pets'
import PetDeployToggle from './PetDeployToggle.vue'
import type { PetAffixPublic, PetPublic } from '../../types/pets'
import { petDisplayName } from '../../utils/petDisplay'

const props = defineProps<{
  pet: PetPublic | null
}>()

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const router = useRouter()
const petsStore = usePetsStore()
const upgrading = ref(false)
const gradingUp = ref(false)
const rerollingSlot = ref<number | null>(null)
const typeRerollingSlot = ref<number | null>(null)
const skillBusy = ref(false)
const draftEquipped = ref<Array<string | null>>([])
const bookIdInput = ref('book_universal_guard')

const affixes = computed(() => props.pet?.affixes ?? [])
const skills = computed(() => props.pet?.skills)
const passives = computed(() => props.pet?.passives)
const feed = computed(() => props.pet?.feed)
const equipSlots = computed(() => skills.value?.equip_slots ?? 4)
const feedingItem = ref<string | null>(null)
const learnedIds = computed(() => skills.value?.learned_ids ?? [])
const poolIds = computed(() => skills.value?.pool_skill_ids ?? [])
const unlearnedPool = computed(() =>
  poolIds.value.filter((id) => !learnedIds.value.includes(id)),
)

watch(
  () => props.pet?.id,
  () => {
    const eq = props.pet?.skills?.equipped_ids
    draftEquipped.value = eq
      ? [...eq]
      : Array.from({ length: equipSlots.value }, () => null)
  },
  { immediate: true },
)

function rerollCost(slotIndex: number): number | null {
  const preview = props.pet?.value_reroll_preview?.find((p) => p.slot_index === slotIndex)
  return preview?.next_cost_spirit_stones ?? null
}

function typeRerollPreview(slotIndex: number) {
  return props.pet?.type_reroll_preview?.find((p) => p.slot_index === slotIndex)
}

function canTypeReroll(slotIndex: number): boolean {
  if (!props.pet?.type_reroll_enabled) return false
  return Boolean(typeRerollPreview(slotIndex)?.eligible)
}

function typeRerollCost(slotIndex: number): number | null {
  return typeRerollPreview(slotIndex)?.next_cost_spirit_stones ?? null
}

function formatAffix(affix: PetAffixPublic): string {
  const name = affix.affix_type_name || affix.affix_type_id
  const kind = affix.kind || ''
  const value = affix.rolled_value
  if (kind.startsWith('pct_')) {
    return `${name}（${affix.affix_tier}）+${value}%`
  }
  if (kind.startsWith('flat_')) {
    return `${name}（${affix.affix_tier}）+${value}`
  }
  return `${name}（${affix.affix_tier}）`
}

function skillLabel(skillId: string): string {
  const hit = skills.value?.learned?.find((s) => s.skill_id === skillId)
  return hit?.name ? `${hit.name}（${skillId}）` : skillId
}

async function onUpgrade(): Promise<void> {
  if (!props.pet || upgrading.value) return
  upgrading.value = true
  try {
    const error = await petsStore.upgrade(props.pet.id)
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    ElMessage.success('升级成功（占位）')
    emit('log', `灵宠 ${petDisplayName(props.pet)} 升级`, 'success')
  } finally {
    upgrading.value = false
  }
}

async function onGradeUp(): Promise<void> {
  if (!props.pet || gradingUp.value) return
  gradingUp.value = true
  try {
    const error = await petsStore.gradeUp(props.pet.id)
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    ElMessage.success('升阶成功')
    emit('log', `灵宠 ${petDisplayName(props.pet)} 升阶`, 'success')
  } finally {
    gradingUp.value = false
  }
}

async function onReroll(slotIndex: number): Promise<void> {
  if (!props.pet || rerollingSlot.value !== null) return
  rerollingSlot.value = slotIndex
  try {
    const error = await petsStore.rerollAffixValue(props.pet.id, slotIndex)
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    ElMessage.success(`槽 ${slotIndex} 数值洗炼完成`)
    emit('log', `词条槽 ${slotIndex} 洗炼`, 'success')
  } finally {
    rerollingSlot.value = null
  }
}

async function onTypeReroll(slotIndex: number): Promise<void> {
  if (!props.pet || typeRerollingSlot.value !== null) return
  typeRerollingSlot.value = slotIndex
  try {
    const error = await petsStore.rerollAffixType(props.pet.id, slotIndex)
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    ElMessage.success(`槽 ${slotIndex} 改类型完成`)
    emit('log', `词条槽 ${slotIndex} 改类型`, 'success')
  } finally {
    typeRerollingSlot.value = null
  }
}

async function onFeed(itemId: string): Promise<void> {
  if (!props.pet || feedingItem.value) return
  feedingItem.value = itemId
  try {
    const error = await petsStore.feed(props.pet.id, itemId, 1)
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    ElMessage.success('喂养成功')
    emit('log', `喂养 ${itemId}`, 'success')
  } finally {
    feedingItem.value = null
  }
}

async function onSaveEquip(): Promise<void> {
  if (!props.pet || skillBusy.value) return
  skillBusy.value = true
  try {
    const error = await petsStore.equipSkills(props.pet.id, [...draftEquipped.value])
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    ElMessage.success('技能装备已保存')
    emit('log', '技能装备更新', 'success')
  } finally {
    skillBusy.value = false
  }
}

async function onLearnPool(skillId: string): Promise<void> {
  if (!props.pet || skillBusy.value) return
  skillBusy.value = true
  try {
    const error = await petsStore.learnFromPool(props.pet.id, skillId)
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    ElMessage.success(`已领悟 ${skillId}`)
    emit('log', `领悟技能 ${skillId}`, 'success')
  } finally {
    skillBusy.value = false
  }
}

async function onLearnBook(): Promise<void> {
  if (!props.pet || skillBusy.value) return
  const bookId = bookIdInput.value.trim()
  if (!bookId) return
  skillBusy.value = true
  try {
    const error = await petsStore.learnFromBook(props.pet.id, bookId)
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    ElMessage.success(`已使用技能书 ${bookId}`)
    emit('log', `技能书 ${bookId}`, 'success')
  } finally {
    skillBusy.value = false
  }
}
</script>

<template>
  <el-card v-if="pet" shadow="never">
    <template #header>
      <el-text tag="b">{{ petDisplayName(pet) }}</el-text>
    </template>

    <el-descriptions :column="1" size="small" border>
      <el-descriptions-item label="物种">{{ pet.species_name || pet.species_id }}</el-descriptions-item>
      <el-descriptions-item label="种族">{{ pet.race_name || pet.race || '—' }}</el-descriptions-item>
      <el-descriptions-item label="稀有度">{{ pet.rarity || '—' }}</el-descriptions-item>
      <el-descriptions-item label="品阶">
        {{ pet.grade_name || pet.grade || '—' }}
        <template v-if="pet.affix_slot_cap">（词条槽 {{ pet.affix_slot_cap }}）</template>
      </el-descriptions-item>
      <el-descriptions-item label="等级">Lv.{{ pet.level }}</el-descriptions-item>
      <el-descriptions-item v-if="pet.stats" label="战力摘要">
        攻 {{ pet.stats.atk }} / 血 {{ pet.stats.hp }} / 速 {{ pet.stats.speed }}
      </el-descriptions-item>
    </el-descriptions>

    <div class="affix-block">
      <el-text tag="b" size="small">词条</el-text>
      <el-empty v-if="affixes.length === 0" description="尚无词条" :image-size="40" />
      <ul v-else class="affix-list">
        <li v-for="affix in affixes" :key="affix.slot_index" class="affix-row">
          <span class="affix-text">槽{{ affix.slot_index }} · {{ formatAffix(affix) }}</span>
          <div class="affix-actions">
            <el-button
              size="small"
              text
              type="primary"
              :loading="rerollingSlot === affix.slot_index"
              @click="onReroll(affix.slot_index)"
            >
              洗炼
              <template v-if="rerollCost(affix.slot_index) != null">
                （{{ rerollCost(affix.slot_index) }} 灵石）
              </template>
            </el-button>
            <el-button
              v-if="canTypeReroll(affix.slot_index)"
              size="small"
              text
              type="warning"
              :loading="typeRerollingSlot === affix.slot_index"
              @click="onTypeReroll(affix.slot_index)"
            >
              改类型
              <template v-if="typeRerollCost(affix.slot_index) != null">
                （{{ typeRerollCost(affix.slot_index) }} 灵石）
              </template>
            </el-button>
          </div>
        </li>
      </ul>
      <el-text type="info" size="small">
        洗炼只改数值；改类型走灵兽宗（品阶解锁前
        {{ pet.type_reroll_slots ?? 1 }} 槽，费用分槽递增）。
        <template v-if="!pet.type_reroll_enabled"> 当前设施未开放。</template>
      </el-text>
    </div>

    <div class="affix-block">
      <el-text tag="b" size="small">被动与种族天赋</el-text>
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="种族天赋">
          <template v-if="passives?.racial_talent">
            {{ passives.racial_talent.name }}
            <el-text type="info" size="small">
              （{{ passives.racial_talent.effect_domain }}）
              {{ passives.racial_talent.summary || '' }}
            </el-text>
          </template>
          <template v-else>—</template>
        </el-descriptions-item>
        <el-descriptions-item label="独立被动">
          <template v-if="passives?.rolled?.length">
            <span v-for="(p, i) in passives.rolled" :key="p.passive_id">
              <template v-if="i > 0">、</template>
              {{ p.name }}（{{ p.effect_domain }}）
            </span>
          </template>
          <el-text v-else type="info" size="small">无（可空）</el-text>
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <div class="affix-block">
      <el-text tag="b" size="small">
        丹药喂养（{{ feed?.total_used ?? 0 }}
        <template v-if="(feed?.total_cap ?? 0) > 0">/ {{ feed?.total_cap }}</template>
        ）
      </el-text>
      <el-empty
        v-if="!feed?.items?.length"
        description="尚无可喂兽丹配置"
        :image-size="40"
      />
      <ul v-else class="egg-list affix-list">
        <li v-for="item in feed?.items" :key="item.item_id" class="affix-row">
          <span class="affix-text">
            {{ item.name }} · 已喂 {{ item.times_fed }}
            <template v-if="item.per_item_cap">/ {{ item.per_item_cap }}</template>
            <el-text type="info" size="small"> {{ item.summary }}</el-text>
          </span>
          <el-button
            size="small"
            text
            type="success"
            :disabled="item.remaining === 0"
            :loading="feedingItem === item.item_id"
            @click="onFeed(item.item_id)"
          >
            喂 1 颗
          </el-button>
        </li>
      </ul>
      <el-text type="info" size="small">超单药或总量上限会拒绝；DEV 发材料附赠兽丹。</el-text>
    </div>

    <div class="affix-block">
      <el-text tag="b" size="small">技能（最多 {{ equipSlots }}）</el-text>
      <div v-for="idx in equipSlots" :key="idx" class="skill-slot">
        <el-text size="small">栏 {{ idx - 1 }}</el-text>
        <el-select
          v-model="draftEquipped[idx - 1]"
          clearable
          placeholder="空槽"
          size="small"
          class="skill-select"
        >
          <el-option
            v-for="sid in learnedIds"
            :key="sid"
            :label="skillLabel(sid)"
            :value="sid"
          />
        </el-select>
      </div>
      <el-button size="small" type="primary" :loading="skillBusy" @click="onSaveEquip">
        保存装备
      </el-button>

      <el-text tag="b" size="small" class="sub-title">物种池可领悟</el-text>
      <div v-if="unlearnedPool.length === 0">
        <el-text type="info" size="small">池内技能均已学会</el-text>
      </div>
      <div v-else class="learn-row">
        <el-button
          v-for="sid in unlearnedPool"
          :key="sid"
          size="small"
          :loading="skillBusy"
          @click="onLearnPool(sid)"
        >
          领悟 {{ sid }}
        </el-button>
      </div>

      <el-text tag="b" size="small" class="sub-title">技能书</el-text>
      <div class="learn-row">
        <el-input v-model="bookIdInput" size="small" placeholder="book_id" class="book-input" />
        <el-button size="small" :loading="skillBusy" @click="onLearnBook">使用技能书</el-button>
      </div>
    </div>

    <div class="actions">
      <el-button size="small" type="primary" :loading="upgrading" @click="onUpgrade">
        升级（占位）
      </el-button>
      <el-button size="small" type="warning" :loading="gradingUp" @click="onGradeUp">
        升阶
      </el-button>
      <PetDeployToggle :pet="pet" @log="(m, l) => emit('log', m, l)" />
      <el-button size="small" @click="router.push('/formation?bench=pet')">去布阵</el-button>
    </div>
  </el-card>

  <el-card v-else shadow="never">
    <el-empty description="选择一只灵宠查看详情" :image-size="56" />
  </el-card>
</template>

<style scoped>
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.affix-block {
  margin-top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.affix-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.affix-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.2rem 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.affix-text {
  font-size: 0.85rem;
}

.affix-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.15rem;
  flex-shrink: 0;
}

.skill-slot {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.skill-select {
  flex: 1;
  min-width: 0;
}

.learn-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: center;
}

.sub-title {
  margin-top: 0.35rem;
}

.book-input {
  max-width: 12rem;
}
</style>
