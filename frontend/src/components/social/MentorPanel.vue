<script setup lang="ts">
/**
 * 师徒面板：申请 / 日课三选一 / 传授 / 出师 / 解除。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useMentorStore } from '../../stores/mentor'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const mentorStore = useMentorStore()
const busy = ref(false)
const targetName = ref('')
const intent = ref<'apprentice' | 'master'>('apprentice')

const lessonKind = ref<'dao' | 'craft' | 'technique'>('dao')
const daoResource = ref<'spirit' | 'body'>('spirit')
const craftTechniqueId = ref('')
const techniqueId = ref('')

const teachKind = ref<'technique' | 'recipe'>('recipe')
const teachItemId = ref('')
const studyTechniqueId = ref('')
const directIds = ref<number[]>([])

const isMaster = computed(() => mentorStore.bond?.role === 'master')
const isDirectBond = computed(() =>
  Boolean(mentorStore.daily?.is_direct || mentorStore.bond?.is_direct),
)
const canAnyLesson = computed(
  () =>
    Boolean(mentorStore.daily?.can_lesson_dao) ||
    Boolean(mentorStore.daily?.can_lesson_craft) ||
    Boolean(mentorStore.daily?.can_lesson_technique),
)

const daoPreview = computed(() => {
  const dao = mentorStore.options?.dao
  if (!dao) return null
  return daoResource.value === 'body' ? dao.body : dao.spirit
})

const craftOptions = computed(() => mentorStore.options?.craft_techniques ?? [])
const techniqueOptions = computed(() => mentorStore.options?.techniques ?? [])
const studyOptions = computed(() => mentorStore.options?.study_techniques ?? [])
const recipeOptions = computed(() => mentorStore.options?.recipes ?? [])

onMounted(async () => {
  const err = await mentorStore.refresh()
  if (err) emit('log', err, 'warning')
  else if (mentorStore.lastMessage?.includes('自动出师')) {
    emit('log', mentorStore.lastMessage, 'system')
  }
  syncDefaults()
  syncDirectIds()
})

function syncDefaults(): void {
  if (!craftTechniqueId.value && craftOptions.value.length) {
    craftTechniqueId.value = craftOptions.value[0].technique_id
  }
  if (!techniqueId.value && techniqueOptions.value.length) {
    techniqueId.value = techniqueOptions.value[0].technique_id
  }
  if (!studyTechniqueId.value && studyOptions.value.length) {
    studyTechniqueId.value = studyOptions.value[0].technique_id
  }
  if (!teachItemId.value) {
    if (teachKind.value === 'recipe' && recipeOptions.value.length) {
      teachItemId.value = recipeOptions.value[0].recipe_id
    } else if (teachKind.value === 'technique' && techniqueOptions.value.length) {
      teachItemId.value = techniqueOptions.value[0].technique_id
    }
  }
}

function syncDirectIds(): void {
  const list = mentorStore.lineage?.disciples ?? []
  directIds.value = list.filter((d) => d.is_direct).map((d) => d.character_id)
}

async function run(fn: () => Promise<string | null>, okHint?: string): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await fn()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    const lines =
      mentorStore.lastLogLines.length > 0
        ? [...mentorStore.lastLogLines]
        : [mentorStore.lastMessage || okHint || '完成']
    ElMessage.success(lines[0] || okHint || '完成')
    for (const line of lines) {
      if (line) emit('log', line, 'success')
    }
    mentorStore.lastLogLines = []
    syncDefaults()
    syncDirectIds()
  } finally {
    busy.value = false
  }
}

async function doLesson(): Promise<void> {
  const daily = mentorStore.daily
  if (lessonKind.value === 'dao' && daily && daily.can_lesson_dao === false) {
    ElMessage.warning('今日传道次数已用完')
    return
  }
  if (lessonKind.value === 'craft' && daily && daily.can_lesson_craft === false) {
    ElMessage.warning('今日授业次数已用完')
    return
  }
  if (lessonKind.value === 'technique' && daily && daily.can_lesson_technique === false) {
    ElMessage.warning('今日解惑次数已用完')
    return
  }
  if (lessonKind.value === 'dao') {
    await run(() =>
      mentorStore.lesson({ kind: 'dao', resource: daoResource.value }),
    )
    return
  }
  if (lessonKind.value === 'craft') {
    if (!craftTechniqueId.value) {
      ElMessage.warning('请选择制造业功法')
      return
    }
    await run(() =>
      mentorStore.lesson({ kind: 'craft', target_id: craftTechniqueId.value }),
    )
    return
  }
  if (!techniqueId.value) {
    ElMessage.warning('请选择功法')
    return
  }
  await run(() =>
    mentorStore.lesson({ kind: 'technique', target_id: techniqueId.value }),
  )
}

async function doTeach(): Promise<void> {
  if (!teachItemId.value) {
    ElMessage.warning('请选择传授内容')
    return
  }
  await run(() =>
    mentorStore.teach({ item_kind: teachKind.value, item_id: teachItemId.value }),
  )
}

async function doStudy(): Promise<void> {
  if (!studyTechniqueId.value) {
    ElMessage.warning('请选择要学习的功法')
    return
  }
  await run(() => mentorStore.study(studyTechniqueId.value))
}

async function doSaveDirect(): Promise<void> {
  const cap = mentorStore.lineage?.direct_cap ?? 3
  if (directIds.value.length > cap) {
    ElMessage.warning(`亲传弟子最多 ${cap} 人`)
    return
  }
  await run(() => mentorStore.setDirect(directIds.value))
}

function onDirectToggle(characterId: number, checked: boolean): void {
  const cap = mentorStore.lineage?.direct_cap ?? 3
  const d = mentorStore.lineage?.disciples.find((x) => x.character_id === characterId)
  if (checked) {
    if (d && d.can_appoint_direct === false) {
      ElMessage.warning(d.direct_lock_reason || '今日不可指定此人')
      return
    }
    if (directIds.value.includes(characterId)) return
    if (directIds.value.length >= cap) {
      ElMessage.warning(`亲传弟子最多 ${cap} 人`)
      return
    }
    directIds.value = [...directIds.value, characterId]
    return
  }
  if (d?.is_direct && d.can_clear_direct === false) {
    ElMessage.warning(d.direct_lock_reason || '指定后需隔日方可解除')
    return
  }
  directIds.value = directIds.value.filter((id) => id !== characterId)
}

function directCheckboxDisabled(d: {
  is_direct: boolean
  can_clear_direct?: boolean
  can_appoint_direct?: boolean
}): boolean {
  if (d.is_direct) return d.can_clear_direct === false
  return d.can_appoint_direct === false
}

function onTeachKindChange(): void {
  teachItemId.value = ''
  syncDefaults()
}

function branchLabel(branch: string): string {
  return (
    {
      alchemy: '丹方',
      smithing: '炼器',
      talisman: '符箓',
      array: '阵法',
      puppet: '傀儡',
    }[branch] || branch
  )
}
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">师徒</el-text>
    </template>

    <div v-if="mentorStore.bond" class="bond">
      <el-text>
        师傅：{{ mentorStore.bond.master_name }} · 徒弟：{{ mentorStore.bond.apprentice_name }}
      </el-text>
      <el-text size="small" type="info">
        你是{{ isMaster ? '师傅' : '徒弟' }}
        <template v-if="mentorStore.channelRef"> · 师承频 {{ mentorStore.channelRef }}</template>
      </el-text>
      <el-text size="small" type="warning">
        收徒须高徒一大境界；弟子追上师傅大境界将自动出师。
      </el-text>

      <div class="quests">
        <div v-for="q in mentorStore.quests" :key="q.quest_id" class="quest">
          <el-text size="small">
            {{ q.name }}：{{ q.progress }}/{{ q.target_count }}
            {{ q.completed ? '（已完成）' : '' }}
          </el-text>
        </div>
      </div>

      <template v-if="isMaster">
        <div class="section">
          <el-text tag="b" size="small">
            日课（传道 / 授业 / 解惑
            {{ isDirectBond ? ' · 亲传授业解惑 +1' : ' · 每日三选一' }}）
          </el-text>
          <el-text v-if="isDirectBond" size="small" type="info">
            传道 {{ mentorStore.daily?.lesson_dao_count ?? 0 }}/{{ mentorStore.daily?.lesson_dao_cap ?? 1 }}
            · 授业 {{ mentorStore.daily?.lesson_craft_count ?? 0 }}/{{ mentorStore.daily?.lesson_craft_cap ?? 1 }}
            · 解惑 {{ mentorStore.daily?.lesson_technique_count ?? 0 }}/{{ mentorStore.daily?.lesson_technique_cap ?? 1 }}
            · 传授次数不变
          </el-text>
          <el-text v-if="!canAnyLesson" size="small" type="success">
            今日日课已用完
            <template v-if="mentorStore.daily?.lesson_kind_label_zh">
              （最近：{{ mentorStore.daily.lesson_kind_label_zh }}）
            </template>
          </el-text>
          <template v-else>
            <el-radio-group v-model="lessonKind" size="small">
              <el-radio-button value="dao" :disabled="mentorStore.daily?.can_lesson_dao === false">
                传道
              </el-radio-button>
              <el-radio-button value="craft" :disabled="mentorStore.daily?.can_lesson_craft === false">
                授业
              </el-radio-button>
              <el-radio-button
                value="technique"
                :disabled="mentorStore.daily?.can_lesson_technique === false"
              >
                解惑
              </el-radio-button>
            </el-radio-group>

            <div v-if="lessonKind === 'dao'" class="sub">
              <el-radio-group v-model="daoResource" size="small">
                <el-radio-button value="spirit">修为</el-radio-button>
                <el-radio-button value="body">炼体度</el-radio-button>
              </el-radio-group>
              <el-text v-if="daoPreview" size="small" type="info">
                预计灌体 {{ daoPreview.preview_amount }}
                （弟子需求 {{ daoPreview.apprentice_need }} · 师傅池 {{ daoPreview.master_pool }}）
              </el-text>
            </div>

            <div v-else-if="lessonKind === 'craft'" class="sub">
              <el-select
                v-model="craftTechniqueId"
                size="small"
                placeholder="制造业功法"
                filterable
                style="width: 100%"
              >
                <el-option
                  v-for="t in craftOptions"
                  :key="t.technique_id"
                  :label="`${t.name}（下级 ${t.next_cost}）`"
                  :value="t.technique_id"
                />
              </el-select>
              <el-text size="small" type="info">
                师傅制造业经验 {{ mentorStore.options?.master_crafting_exp ?? 0 }}
              </el-text>
            </div>

            <div v-else class="sub">
              <el-select
                v-model="techniqueId"
                size="small"
                placeholder="功法"
                filterable
                style="width: 100%"
              >
                <el-option
                  v-for="t in techniqueOptions"
                  :key="t.technique_id"
                  :label="`${t.name}（${t.track} · 下级 ${t.next_cost}）`"
                  :value="t.technique_id"
                />
              </el-select>
            </div>

            <el-button type="primary" size="small" :loading="busy" @click="doLesson">
              开始日课
            </el-button>
          </template>
        </div>

        <div class="section">
          <el-text tag="b" size="small">传授（功法 / 丹方图纸 · 每日一次，可多日累计）</el-text>
          <el-text v-if="mentorStore.daily?.teach_done" size="small" type="success">
            今日传授已用完（{{ mentorStore.daily.teach_count }}/{{ mentorStore.daily.teach_cap }}）
          </el-text>
          <template v-else>
            <el-radio-group v-model="teachKind" size="small" @change="onTeachKindChange">
              <el-radio-button value="recipe">配方图纸</el-radio-button>
              <el-radio-button value="technique">功法</el-radio-button>
            </el-radio-group>
            <el-select
              v-if="teachKind === 'recipe'"
              v-model="teachItemId"
              size="small"
              placeholder="选择丹方/炼器/符箓/阵法/傀儡"
              filterable
              style="width: 100%"
            >
              <el-option
                v-for="r in recipeOptions"
                :key="r.recipe_id"
                :label="`${r.name}（${branchLabel(r.branch)} · 需 ${r.required_sessions} 日）`"
                :value="r.recipe_id"
              />
            </el-select>
            <el-select
              v-else
              v-model="teachItemId"
              size="small"
              placeholder="选择功法"
              filterable
              style="width: 100%"
            >
              <el-option
                v-for="t in techniqueOptions"
                :key="t.technique_id"
                :label="t.name"
                :value="t.technique_id"
              />
            </el-select>
            <el-button type="primary" size="small" :loading="busy" @click="doTeach">
              今日传授
            </el-button>
          </template>

          <div v-if="mentorStore.transmissions.length" class="tx-list">
            <el-text size="small" type="info">进行中 / 已完成</el-text>
            <div
              v-for="tx in mentorStore.transmissions"
              :key="`${tx.item_kind}:${tx.item_id}`"
              class="tx"
            >
              <el-text size="small">
                {{ tx.name }}：{{ tx.progress }}/{{ tx.required_sessions }}
                {{ tx.status === 'completed' ? '（完成）' : '' }}
              </el-text>
            </div>
          </div>
        </div>
      </template>

      <template v-else>
        <div class="section">
          <el-text tag="b" size="small">请学功法（指定师傅功法 · 每日一次）</el-text>
          <el-text size="small" type="info">
            可选择师傅正在传授、尚未学完的同种功法，额外推进学习进度。
          </el-text>
          <el-text v-if="mentorStore.daily?.study_done" size="small" type="success">
            今日请学已用完（{{ mentorStore.daily.study_count }}/{{ mentorStore.daily.study_cap }}）
          </el-text>
          <template v-else>
            <el-select
              v-model="studyTechniqueId"
              size="small"
              placeholder="选择师傅功法"
              filterable
              style="width: 100%"
            >
              <el-option
                v-for="t in studyOptions"
                :key="t.technique_id"
                :label="`${t.name}（师傅 Lv.${t.master_level ?? '?'}）`"
                :value="t.technique_id"
              />
            </el-select>
            <el-button type="primary" size="small" :loading="busy" @click="doStudy">
              今日请学
            </el-button>
          </template>

          <div v-if="mentorStore.transmissions.length" class="tx-list">
            <el-text size="small" type="info">传授 / 请学进度</el-text>
            <div
              v-for="tx in mentorStore.transmissions"
              :key="`appr-${tx.item_kind}:${tx.item_id}`"
              class="tx"
            >
              <el-text size="small">
                {{ tx.name }}：{{ tx.progress }}/{{ tx.required_sessions }}
                {{ tx.status === 'completed' ? '（完成）' : '' }}
              </el-text>
            </div>
          </div>
        </div>
      </template>

      <div class="actions">
        <el-button
          size="small"
          type="success"
          :loading="busy"
          @click="run(() => mentorStore.graduate())"
        >
          出师
        </el-button>
        <el-button size="small" :loading="busy" @click="run(() => mentorStore.dissolve())">
          解除
        </el-button>
      </div>
    </div>

    <div v-else class="apply">
      <el-radio-group v-model="intent" size="small">
        <el-radio-button value="apprentice">拜师</el-radio-button>
        <el-radio-button value="master">收徒</el-radio-button>
      </el-radio-group>
      <el-input v-model="targetName" size="small" placeholder="对方道号" clearable />
      <el-button
        type="primary"
        size="small"
        :loading="busy"
        @click="run(() => mentorStore.apply(targetName, intent))"
      >
        发送申请
      </el-button>
    </div>

    <div v-if="mentorStore.lineage" class="section lineage">
      <el-text tag="b" size="small">
        师承单 · {{ mentorStore.lineage.master_name }}
      </el-text>
      <el-text size="small" type="info">
        按拜师时间排序；亲传最多 {{ mentorStore.lineage.direct_cap }} 人（授业/解惑 +1）；
        指定后隔日可解除，解除当日不可再指定；出师自动解除亲传
      </el-text>
      <div
        v-for="d in mentorStore.lineage.disciples"
        :key="d.bond_id"
        class="lineage-row"
      >
        <el-checkbox
          v-if="mentorStore.lineage.can_set_direct"
          :model-value="directIds.includes(d.character_id)"
          :disabled="directCheckboxDisabled(d)"
          @change="(v: boolean | string | number) => onDirectToggle(d.character_id, Boolean(v))"
        >
          亲传
        </el-checkbox>
        <el-text size="small">
          {{ d.ordinal_title_zh }} · {{ d.display_name }}
          <template v-if="d.is_direct && !mentorStore.lineage.can_set_direct"> · 亲传</template>
          <template v-if="d.direct_lock_reason"> · {{ d.direct_lock_reason }}</template>
        </el-text>
      </div>
      <el-button
        v-if="mentorStore.lineage.can_set_direct"
        type="primary"
        size="small"
        :loading="busy"
        @click="doSaveDirect"
      >
        保存亲传（{{ directIds.length }}/{{ mentorStore.lineage.direct_cap }}）
      </el-button>
    </div>

    <div v-if="mentorStore.incoming.length" class="inbox">
      <el-text tag="b" size="small">待确认</el-text>
      <div v-for="b in mentorStore.incoming" :key="b.bond_id" class="row">
        <el-text size="small">
          {{ b.master_name }} ← {{ b.apprentice_name }}
        </el-text>
        <el-button size="small" type="primary" @click="run(() => mentorStore.accept(b.bond_id))">
          确认
        </el-button>
        <el-button size="small" @click="run(() => mentorStore.reject(b.bond_id))">拒绝</el-button>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.bond,
.apply,
.inbox,
.section,
.sub {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}
.section {
  margin-top: 0.35rem;
  padding-top: 0.45rem;
  border-top: 1px dashed var(--el-border-color-lighter);
}
.actions,
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: center;
}
.quests,
.tx-list,
.lineage {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.lineage {
  margin-top: 0.75rem;
  padding-top: 0.5rem;
  border-top: 1px dashed var(--el-border-color-lighter);
  gap: 0.35rem;
}
.lineage-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
}
.inbox {
  margin-top: 0.75rem;
  padding-top: 0.5rem;
  border-top: 1px dashed var(--el-border-color-lighter);
}
</style>
