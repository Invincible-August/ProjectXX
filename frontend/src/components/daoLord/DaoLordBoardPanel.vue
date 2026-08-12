<script setup lang="ts">
/**
 * 道主榜：空位自动就任；有主时引导赛会报名。
 */
import { computed } from 'vue'
import type { DaoLordSeatPublic } from '../../types/daoLord'
import { daoLabel } from '../../utils/daoLabel'

const props = defineProps<{
  seats: DaoLordSeatPublic[]
  windowOpen: boolean
  wsReady: boolean
  focusDaoId?: string | null
  busy?: boolean
  /**
   * 是否展示榜上/工具栏「报名」入口。
   * 未满足报名资格时为 false（不出现「去报名」字样）。
   */
  showContestRegister?: boolean
}>()

const emit = defineEmits<{
  contest: []
}>()

const rows = computed(() => props.seats)

/** 工具栏「道主之争报名」：显式 prop 优先，否则看是否有任一席位可报名 */
const showToolbarRegister = computed(() => {
  if (props.showContestRegister === false) return false
  if (props.showContestRegister === true) return true
  return rows.value.some((s) => showRegisterCta(s))
})

function seatLabel(seat: DaoLordSeatPublic): string {
  return daoLabel(seat.dao_id, seat.dao_label)
}

function claimedText(seat: DaoLordSeatPublic): string {
  if (!seat.claimed_at) return '—'
  try {
    return new Date(seat.claimed_at).toLocaleString('zh-CN')
  } catch {
    return seat.claimed_at
  }
}

function hintText(seat: DaoLordSeatPublic): string | null {
  if (seat.is_self_lord) return '你是本道道主'
  if (seat.vacant || !seat.lord_character_id) {
    return seat.claim_block_reason || '空位：本命道达标者自动就任'
  }
  // 有主：仅达标可报名时提示去赛会；未达标只显示拦截原因
  if (seat.can_challenge) {
    return '有主：可报名道主之争（淘汰后决战道主）'
  }
  return seat.challenge_block_reason || seat.block_reason || null
}

/** 本行是否展示「去报名」：有主、非本人、且满足挑战/报名资格 */
function showRegisterCta(seat: DaoLordSeatPublic): boolean {
  return Boolean(seat.lord_character_id && !seat.is_self_lord && seat.can_challenge)
}
</script>

<template>
  <el-card shadow="never" class="board">
    <template #header>
      <el-text tag="b">道主榜</el-text>
    </template>

    <el-alert
      class="intro"
      type="info"
      :closable="false"
      show-icon
      title="空位自动就任。有道主后请报名道主之争（报名→淘汰→决战）；半决赛/决赛直播见后续版本。"
    />

    <div v-if="showToolbarRegister" class="toolbar">
      <el-button type="primary" size="small" :disabled="busy" @click="emit('contest')">
        道主之争报名
      </el-button>
    </div>

    <el-empty v-if="!rows.length" description="暂无道主座位数据" :image-size="48" />

    <el-table v-else :data="rows" size="small" stripe>
      <el-table-column label="大道" min-width="100">
        <template #default="{ row }">
          <el-text :type="focusDaoId === row.dao_id ? 'primary' : undefined" tag="b">
            {{ seatLabel(row) }}
          </el-text>
        </template>
      </el-table-column>
      <el-table-column label="道主" min-width="100">
        <template #default="{ row }">
          {{ row.lord_name || '虚位以待' }}
        </template>
      </el-table-column>
      <el-table-column label="就任" min-width="140">
        <template #default="{ row }">
          {{ claimedText(row) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="showRegisterCta(row)"
            type="primary"
            size="small"
            :disabled="busy"
            @click="emit('contest')"
          >
            去报名
          </el-button>
          <el-text v-else-if="row.vacant || !row.lord_character_id" size="small" type="info">
            虚位
          </el-text>
          <el-text v-if="hintText(row)" size="small" type="warning" class="block">
            {{ hintText(row) }}
          </el-text>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<style scoped>
.intro {
  margin-bottom: 0.75rem;
}
.toolbar {
  margin-bottom: 0.75rem;
}
.block {
  display: block;
  margin-top: 0.25rem;
}
</style>
