<script setup lang="ts">
/**
 * 议事厅：俸禄 / 自荐 / 任命 / 公告 / 升级与增益（权限可见）/ 战占位。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  announceSect,
  applySectRank,
  appointSectRank,
  claimSectSalary,
  fetchRankApplications,
  fetchSectMembers,
  fetchSectOverview,
  startSectWar,
  toggleSectBuff,
  upgradeSectFacility,
  upgradeSectGrade,
} from '../../api/sect'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const overview = ref<Record<string, any> | null>(null)
const members = ref<any[]>([])
const apps = ref<any[]>([])
const announceText = ref('')
const applyRank = ref('outer_disciple')
const appointCharId = ref<number | null>(null)
const appointRank = ref('inner_deacon')
const busy = ref(false)

const selfApplyRanks = [
  { value: 'outer_disciple', label: '外门弟子' },
  { value: 'inner_disciple', label: '内门弟子' },
  { value: 'core_disciple', label: '亲传弟子' },
  { value: 'outer_deacon', label: '外门执事' },
  { value: 'outer_elder', label: '外门长老' },
  { value: 'inner_deacon', label: '内门执事（自荐）' },
  { value: 'inner_elder', label: '内门长老（自荐）' },
]

const canUpgrade = computed(() => {
  const actions: string[] = overview.value?.my_actions || []
  return (
    actions.includes('upgrade_grade') ||
    actions.includes('upgrade_facility') ||
    actions.includes('toggle_buff')
  )
})

async function reload(): Promise<void> {
  const [ov, mem, ap] = await Promise.all([
    fetchSectOverview(),
    fetchSectMembers(),
    fetchRankApplications(),
  ])
  if (ov.code === 0) overview.value = ov.data || null
  if (mem.code === 0) members.value = (mem.data?.items as any[]) || []
  if (ap.code === 0) apps.value = (ap.data?.items as any[]) || []
  if (overview.value?.announcement) {
    announceText.value = String(overview.value.announcement)
  }
}

async function onSalary(): Promise<void> {
  busy.value = true
  try {
    const env = await claimSectSalary()
    if (env.code !== 0) {
      ElMessage.error(env.message || '领取失败')
      return
    }
    ElMessage.success(String(env.data?.message || '已领取'))
    emit('log', String(env.data?.message || '已领取'), 'success')
    await reload()
  } finally {
    busy.value = false
  }
}

async function onApply(): Promise<void> {
  const env = await applySectRank({ target_rank: applyRank.value })
  if (env.code !== 0) {
    ElMessage.error(env.message || '申请失败')
    return
  }
  ElMessage.success(String(env.data?.message || '已申请'))
  emit('log', String(env.data?.message || '已申请'), 'success')
  await reload()
}

async function onAppoint(): Promise<void> {
  if (!appointCharId.value) {
    ElMessage.warning('请选择门众')
    return
  }
  const env = await appointSectRank({
    target_character_id: appointCharId.value,
    target_rank: appointRank.value,
  })
  if (env.code !== 0) {
    ElMessage.error(env.message || '任命失败')
    return
  }
  ElMessage.success(String(env.data?.message || '已任命'))
  await reload()
}

async function onAnnounce(): Promise<void> {
  const env = await announceSect({ text_zh: announceText.value })
  if (env.code !== 0) {
    ElMessage.error(env.message || '发布失败')
    return
  }
  ElMessage.success('公告已更新')
  await reload()
}

async function onWar(kind: string): Promise<void> {
  const env = await startSectWar({ war_kind: kind })
  ElMessage.warning(env.message || '战事未开放（M11）')
  emit('log', env.message || '战事未开放', 'warning')
}

async function onUpgradeGrade(): Promise<void> {
  const env = await upgradeSectGrade()
  if (env.code !== 0) {
    ElMessage.error(env.message || '升等失败')
    emit('log', env.message || '升等失败', 'warning')
    return
  }
  ElMessage.success(String(env.data?.message || '已升等'))
  emit('log', String(env.data?.message || '已升等'), 'success')
  await reload()
}

async function onUpgradeFacility(fid: string): Promise<void> {
  const env = await upgradeSectFacility(fid)
  if (env.code !== 0) {
    ElMessage.error(env.message || '升级失败')
    emit('log', env.message || '升级失败', 'warning')
    return
  }
  ElMessage.success(String(env.data?.message || '已升级'))
  emit('log', String(env.data?.message || '已升级'), 'success')
  await reload()
}

async function onToggleBuff(buffId: string, enable: boolean): Promise<void> {
  const env = await toggleSectBuff({ buff_id: buffId, enable })
  if (env.code !== 0) {
    ElMessage.error(env.message || '操作失败')
    emit('log', env.message || '操作失败', 'warning')
    return
  }
  ElMessage.success(String(env.data?.message || '已更新'))
  await reload()
}

onMounted(() => {
  void reload()
})
</script>

<template>
  <div class="council">
    <el-card shadow="never">
      <template #header>
        <el-text tag="b">议事厅</el-text>
      </template>
      <el-text v-if="overview" size="small" type="info">
        职位 {{ overview.my_rank_label_zh }} · 可执行：{{
          (overview.my_actions || []).join('、') || '无'
        }}
      </el-text>
      <div class="row">
        <el-button type="primary" :loading="busy" @click="onSalary">领取日俸</el-button>
        <el-button
          :disabled="!(overview?.my_actions || []).includes('war_start')"
          @click="onWar('sect_war')"
        >
          发起宗门战（占位）
        </el-button>
        <el-button
          :disabled="!(overview?.my_actions || []).includes('war_start')"
          @click="onWar('force_war')"
        >
          发起势力战（占位）
        </el-button>
      </div>
    </el-card>

    <el-card v-if="canUpgrade" shadow="never">
      <template #header>
        <el-text tag="b">升级与增益</el-text>
      </template>
      <el-text size="small" type="info">
        当前 {{ overview?.grade_label_zh }}
        <template v-if="overview?.next_grade">
          → 下一档 {{ overview.next_grade.label_zh }}
        </template>
        · 灵石库 {{ overview?.spirit_stone_pool }}
      </el-text>
      <div class="row">
        <el-button
          type="warning"
          :disabled="!(overview?.my_actions || []).includes('upgrade_grade')"
          @click="onUpgradeGrade"
        >
          升宗门等级
        </el-button>
      </div>
      <el-divider content-position="left">设施升级</el-divider>
      <div
        v-for="f in overview?.facilities || []"
        :key="f.facility_id"
        class="fac-row"
      >
        <el-text>{{ f.label_zh }} Lv.{{ f.level }}/{{ f.max_level }}</el-text>
        <el-button
          size="small"
          :disabled="!(overview?.my_actions || []).includes('upgrade_facility')"
          @click="onUpgradeFacility(f.facility_id)"
        >
          升级
        </el-button>
      </div>
      <el-divider content-position="left">
        宗门增益（最多 {{ overview?.max_active_buffs }}）
      </el-divider>
      <div
        v-for="b in overview?.buff_catalog || []"
        :key="b.buff_id"
        class="fac-row"
      >
        <el-text>
          {{ b.label_zh }} · 档{{ b.tier }} · 日耗 {{ b.cost_spirit_stones_per_day }}
        </el-text>
        <el-button
          size="small"
          :type="b.active ? 'danger' : 'primary'"
          :disabled="!(overview?.my_actions || []).includes('toggle_buff')"
          @click="onToggleBuff(b.buff_id, !b.active)"
        >
          {{ b.active ? '关闭' : '开启' }}
        </el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <el-text tag="b">晋升申请 / 毛遂自荐</el-text>
      </template>
      <div class="row">
        <el-select v-model="applyRank" style="min-width: 180px">
          <el-option
            v-for="r in selfApplyRanks"
            :key="r.value"
            :label="r.label"
            :value="r.value"
          />
        </el-select>
        <el-button @click="onApply">提交申请</el-button>
      </div>
      <el-table :data="apps.slice(0, 8)" size="small" style="margin-top: 0.5rem">
        <el-table-column prop="name" label="弟子" />
        <el-table-column prop="target_rank_label_zh" label="目标" />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column prop="apply_game_day" label="申请日" width="80" />
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <el-text tag="b">任命</el-text>
      </template>
      <div class="row">
        <el-select
          v-model="appointCharId"
          placeholder="选择门众"
          style="min-width: 160px"
          :disabled="!(overview?.my_actions || []).includes('appoint')"
        >
          <el-option
            v-for="m in members"
            :key="m.character_id"
            :label="`${m.name}（${m.rank_label_zh}）`"
            :value="m.character_id"
          />
        </el-select>
        <el-select
          v-model="appointRank"
          style="min-width: 140px"
          :disabled="!(overview?.my_actions || []).includes('appoint')"
        >
          <el-option label="内门执事" value="inner_deacon" />
          <el-option label="内门长老" value="inner_elder" />
          <el-option label="掌门" value="leader" />
          <el-option label="大长老" value="grand_elder" />
          <el-option label="太上长老" value="supreme_elder" />
        </el-select>
        <el-button
          type="warning"
          :disabled="!(overview?.my_actions || []).includes('appoint')"
          @click="onAppoint"
        >
          任命
        </el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <el-text tag="b">宗门公告</el-text>
      </template>
      <el-input
        v-model="announceText"
        type="textarea"
        :rows="3"
        maxlength="200"
        show-word-limit
        :disabled="!(overview?.my_actions || []).includes('announce')"
      />
      <el-button
        style="margin-top: 0.5rem"
        :disabled="!(overview?.my_actions || []).includes('announce')"
        @click="onAnnounce"
      >
        发布
      </el-button>
    </el-card>
  </div>
</template>

<style scoped>
.council {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
  align-items: center;
}
.fac-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.35rem;
}
</style>
