<script setup lang="ts">
/**
 * 开道三选一面板：展示服务端冻结选项；提交 choose。
 * 禁止客户端本地抽道。
 */
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useDaoStore } from '../../stores/dao'
import { useCharacterStore } from '../../stores/character'
import type { DaoCatalogEntry } from '../../types/dao'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
  chosen: []
}>()

const daoStore = useDaoStore()
const characterStore = useCharacterStore()

const busy = ref(false)
const selectedId = ref<string | null>(null)
/** 道池自选 Tab（再开时） */
const pickTab = ref<'roll' | 'pool'>('roll')

const options = computed(() => daoStore.opening?.options ?? [])
const allowPoolPick = computed(() => Boolean(daoStore.opening?.allow_pool_pick))
const awaitingFerry = computed(
  () => characterStore.character?.status === 'awaiting_ferry',
)
const inTribulation = computed(
  () => characterStore.character?.status === 'tribulation',
)
/** 待引渡禁 POST；渡劫中允许只读看池，禁开道写 */
const writeBlocked = computed(() => awaitingFerry.value || inTribulation.value)

async function onRoll(): Promise<void> {
  if (busy.value || writeBlocked.value) return
  busy.value = true
  try {
    const err = await daoStore.roll()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    selectedId.value = null
    pickTab.value = 'roll'
    ElMessage.success('三道已现，择一为本命')
    emit('log', '开道抽取：三选项已冻结', 'info')
  } finally {
    busy.value = false
  }
}

async function onChoose(entry: DaoCatalogEntry): Promise<void> {
  if (busy.value || writeBlocked.value) return
  try {
    await ElMessageBox.confirm(
      `确认将「${entry.label}」锁定为本周目本命大道？选定后不可更改。`,
      '选定本命道',
      { type: 'warning', confirmButtonText: '确认锁定', cancelButtonText: '再想想' },
    )
  } catch {
    return
  }
  busy.value = true
  try {
    const err = await daoStore.choose(entry.dao_id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(daoStore.lastMessage || `开道成功：${entry.label}`)
    emit('log', daoStore.lastMessage || `开道成功：${entry.label}`, 'success')
    emit('chosen')
  } finally {
    busy.value = false
  }
}

function onSelectCard(entry: DaoCatalogEntry): void {
  selectedId.value = entry.dao_id
}
</script>

<template>
  <el-card shadow="never" class="dao-open">
    <template #header>
      <div class="hdr">
        <el-text tag="b">开辟本命大道</el-text>
        <el-button
          type="primary"
          size="small"
          :loading="busy"
          :disabled="writeBlocked || Boolean(daoStore.me?.locked)"
          @click="onRoll"
        >
          抽取三道
        </el-button>
      </div>
    </template>

    <el-alert
      class="hint"
      type="info"
      :closable="false"
      show-icon
      title="抽出的三道将全部录入道池，跨轮回保留；本周目本命道选定后不可更改。"
    />

    <el-alert
      v-if="writeBlocked"
      class="hint"
      type="warning"
      :closable="false"
      show-icon
      :title="
        awaitingFerry
          ? '待引渡期间不可开道，可只读浏览'
          : '渡劫进行中不可开道写操作'
      "
    />

    <el-alert
      v-else-if="daoStore.me && !daoStore.me.can_open && !daoStore.me.locked"
      class="hint"
      type="warning"
      :closable="false"
      show-icon
      title="抵达真仙后方可开道；可先浏览图鉴样本"
    />

    <el-tabs v-if="allowPoolPick && daoStore.opening" v-model="pickTab" class="tabs">
      <el-tab-pane label="三选一" name="roll" />
      <el-tab-pane label="道池自选" name="pool" />
    </el-tabs>

    <div v-if="pickTab === 'roll' || !allowPoolPick" class="cards">
      <el-empty
        v-if="!options.length"
        description="尚未抽取；点击「抽取三道」由天道定夺"
        :image-size="56"
      />
      <TransitionGroup v-else name="dao-flip" tag="div" class="card-row">
        <div
          v-for="(opt, idx) in options"
          :key="opt.dao_id"
          class="dao-card"
          :class="{ selected: selectedId === opt.dao_id }"
          :style="{ animationDelay: `${idx * 80}ms` }"
          @click="onSelectCard(opt)"
        >
          <el-text tag="b">{{ opt.label }}</el-text>
          <el-text size="small" type="info">
            {{ opt.category_label }} · {{ opt.rarity_label }}
          </el-text>
          <el-text v-if="opt.description" size="small">{{ opt.description }}</el-text>
          <el-tag v-if="opt.owned" size="small" type="success">已在道池</el-tag>
          <el-button
            type="primary"
            size="small"
            :disabled="writeBlocked || busy"
            @click.stop="onChoose(opt)"
          >
            选定为本命道
          </el-button>
        </div>
      </TransitionGroup>
    </div>

    <div v-else class="pool-pick">
      <el-empty
        v-if="!daoStore.pool.length"
        description="道池为空"
        :image-size="48"
      />
      <div v-else class="pool-list">
        <el-button
          v-for="p in daoStore.pool"
          :key="p.dao_id"
          size="small"
          :disabled="writeBlocked || busy"
          @click="onChoose(p)"
        >
          {{ p.label }}
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.hdr {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.hint {
  margin-bottom: 0.75rem;
}

.tabs {
  margin-bottom: 0.5rem;
}

.card-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 0.75rem;
}

.dao-card {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  padding: 0.75rem;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  cursor: pointer;
  animation: dao-flip-in 0.35s ease both;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.dao-card:hover {
  border-color: var(--el-color-primary-light-3);
}

.dao-card.selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-5);
}

.pool-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

@keyframes dao-flip-in {
  from {
    opacity: 0;
    transform: translateY(8px) rotateX(-8deg);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

.dao-flip-enter-active {
  animation: dao-flip-in 0.35s ease;
}
</style>
