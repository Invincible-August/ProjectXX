<script setup lang="ts">
/**
 * 双修工作台面板：会话 / 四榜（可嵌社交页或独立双修页）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useDualCultivationStore } from '../../stores/dualCultivation'
import type { DualGender } from '../../types/dualCultivation'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const dualStore = useDualCultivationStore()

const busy = ref(false)
const targetName = ref('')
const techniqueId = ref('')
const genderPick = ref<DualGender>('male')
const activeBoard = ref('male_number_one')
const tab = ref<'session' | 'ranks'>('session')

const boardKeys = computed(() =>
  dualStore.ranks ? Object.keys(dualStore.ranks.boards) : [],
)

const currentBoard = computed(() => {
  if (!dualStore.ranks) return null
  return dualStore.ranks.boards[activeBoard.value] || null
})

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
    ElMessage.success(okHint || dualStore.lastMessage || '完成')
    emit('log', dualStore.lastMessage || okHint || '完成', 'success')
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  await dualStore.refreshMe()
  if (dualStore.techniques.length && !techniqueId.value) {
    techniqueId.value = dualStore.techniques[0].technique_id
  }
  await dualStore.loadRanks()
  if (boardKeys.value.length) {
    activeBoard.value = boardKeys.value[0]
  }
  emit('log', '双修工作台已就绪', 'info')
})

watch(
  () => dualStore.techniques,
  (list) => {
    if (list.length && !techniqueId.value) {
      techniqueId.value = list[0].technique_id
    }
  },
)
</script>

<template>
  <div class="dual-panel">
    <div class="sub-nav">
      <el-button
        size="small"
        :type="tab === 'session' ? 'primary' : 'default'"
        @click="tab = 'session'"
      >
        会话
      </el-button>
      <el-button
        size="small"
        :type="tab === 'ranks' ? 'primary' : 'default'"
        @click="tab = 'ranks'"
      >
        四榜
      </el-button>
    </div>

    <el-card v-if="dualStore.me?.needs_gender" shadow="never">
      <template #header>
        <el-text tag="b">补全道途阴阳</el-text>
      </template>
      <el-text size="small" type="info" class="hint">
        进双修与上榜前须选定性别；选定后不可自行更改。
      </el-text>
      <el-radio-group v-model="genderPick" size="small">
        <el-radio-button value="male">乾道（男）</el-radio-button>
        <el-radio-button value="female">坤道（女）</el-radio-button>
      </el-radio-group>
      <el-button
        type="primary"
        size="small"
        class="mt"
        :loading="busy"
        @click="run(() => dualStore.chooseGender(genderPick), '阴阳已定')"
      >
        确认
      </el-button>
    </el-card>

    <template v-else-if="tab === 'session'">
      <el-card shadow="never">
        <template #header>
          <el-text tag="b">当前阴阳</el-text>
        </template>
        <el-text>{{ dualStore.me?.gender_label_zh || '—' }}</el-text>
      </el-card>

      <el-card v-if="dualStore.session" shadow="never" class="mt">
        <template #header>
          <el-text tag="b">进行中会话</el-text>
        </template>
        <el-text>
          {{ dualStore.session.technique_label }} · {{ dualStore.session.status }}
        </el-text>
        <el-text size="small" type="info" class="hint">
          {{ dualStore.session.inviter.name }} ↔ {{ dualStore.session.invitee.name }}
        </el-text>
        <div v-if="dualStore.session.dice" class="dice-box">
          <el-text>
            掷骰：{{ dualStore.session.dice.label_zh || dualStore.session.dice.effect_tier }}
            （{{ dualStore.session.dice.roll }} · 倍率
            {{ dualStore.session.dice.yield_mult }}）
          </el-text>
        </div>
        <div class="actions">
          <el-button
            v-if="dualStore.session.status === 'inviting'"
            size="small"
            type="primary"
            :loading="busy"
            @click="run(() => dualStore.confirm(dualStore.session!.session_id))"
          >
            确认邀约
          </el-button>
          <el-button
            v-if="
              dualStore.session.status === 'confirmed' ||
              dualStore.session.status === 'running'
            "
            size="small"
            type="warning"
            :loading="busy"
            @click="run(() => dualStore.roll(dualStore.session!.session_id))"
          >
            掷骰
          </el-button>
          <el-button
            v-if="dualStore.session.status === 'running'"
            size="small"
            type="success"
            :loading="busy"
            @click="run(() => dualStore.settle(dualStore.session!.session_id))"
          >
            结算领取
          </el-button>
          <el-button
            size="small"
            :loading="busy"
            @click="run(() => dualStore.cancel(dualStore.session!.session_id))"
          >
            取消
          </el-button>
        </div>
      </el-card>

      <el-card v-else shadow="never" class="mt">
        <template #header>
          <el-text tag="b">发起双修</el-text>
        </template>
        <el-select v-model="techniqueId" size="small" placeholder="选择功法">
          <el-option
            v-for="t in dualStore.techniques"
            :key="t.technique_id"
            :label="`${t.label}（${t.mode === 'mutual_gain' ? '双增' : '传修为'}）`"
            :value="t.technique_id"
          />
        </el-select>
        <el-input
          v-model="targetName"
          size="small"
          class="mt"
          placeholder="对方道号"
          clearable
        />
        <el-button
          type="primary"
          size="small"
          class="mt"
          :loading="busy"
          :disabled="!techniqueId || !targetName.trim()"
          @click="run(() => dualStore.invite(techniqueId, targetName))"
        >
          发送邀约
        </el-button>
      </el-card>
    </template>

    <el-card v-else shadow="never">
      <template #header>
        <el-text tag="b">四榜</el-text>
      </template>
      <el-radio-group v-model="activeBoard" size="small" class="boards">
        <el-radio-button v-for="k in boardKeys" :key="k" :value="k">
          {{ dualStore.ranks?.boards[k]?.label_zh || k }}
        </el-radio-button>
      </el-radio-group>
      <el-text v-if="currentBoard" size="small" type="info" class="hint">
        本人：第 {{ currentBoard.my_rank ?? '—' }} 名 · 分
        {{ currentBoard.my_score }}（门槛 {{ currentBoard.min_score }}）
      </el-text>
      <el-table
        v-if="currentBoard"
        :data="currentBoard.entries"
        size="small"
        empty-text="尚无上榜"
      >
        <el-table-column prop="rank" label="名次" width="70" />
        <el-table-column prop="name" label="道号" />
        <el-table-column prop="score" label="积分" width="90" />
      </el-table>
      <el-button size="small" class="mt" @click="dualStore.loadRanks()">刷新</el-button>
    </el-card>
  </div>
</template>

<style scoped>
.dual-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.sub-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.hint {
  display: block;
  margin: 0.35rem 0 0.6rem;
}
.mt {
  margin-top: 0.5rem;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.6rem;
}
.dice-box {
  margin-top: 0.5rem;
  padding: 0.4rem 0.5rem;
  background: var(--el-fill-color-light);
}
.boards {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  margin-bottom: 0.5rem;
}
</style>
