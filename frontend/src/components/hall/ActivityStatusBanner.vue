<script setup lang="ts">
/**
 * 大厅活动态一行提示（显性：当前占用）。
 */
import { useActivityGate } from '../../composables/useActivityGate'

const { activity, modeLabel } = useActivityGate()
</script>

<template>
  <el-alert
    v-if="activity.mode !== 'free'"
    :title="`当前状态：${modeLabel}`"
    :type="activity.mode === 'idle' ? 'success' : 'warning'"
    show-icon
    :closable="false"
    class="activity-banner"
  >
    <template v-if="activity.mode === 'idle'" #default>
      <el-text size="small">
        <template v-if="activity.idle_direction === 'sect_mining'">
          采矿中无法开战、炼丹炼器、突破或渡劫；请先在修炼区结束采矿（或于矿脉停止）。
        </template>
        <template v-else>
          修炼中无法开战、炼丹炼器、突破或渡劫；请先在修炼区停止修炼。
        </template>
      </el-text>
    </template>
    <template v-else-if="activity.mode === 'craft'" #default>
      <el-text size="small">
        工坊进行中无法进入修炼；请等待任务完成或领取后再修炼。
      </el-text>
    </template>
    <template v-else-if="activity.mode === 'breaking_through'" #default>
      <el-text size="small">
        突破结算中，请稍候片刻。
      </el-text>
    </template>
  </el-alert>
</template>

<style scoped>
.activity-banner {
  margin: 0.35rem 0 0.5rem;
}
</style>
