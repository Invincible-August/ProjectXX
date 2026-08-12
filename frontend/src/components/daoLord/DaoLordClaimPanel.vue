<script setup lang="ts">
/**
 * 空位说明：达标自动就任，无需手动夺位（保留组件以免旧引用炸掉）。
 */
import { daoLabel } from '../../utils/daoLabel'

defineProps<{
  daoId: string
  daoLabelText?: string | null
}>()
</script>

<template>
  <el-card shadow="never" class="claim">
    <template #header>
      <el-text tag="b">空位就任</el-text>
    </template>
    <el-alert
      type="success"
      :closable="false"
      show-icon
      :title="`「${daoLabel(daoId, daoLabelText)}」虚位以待：本命道相符且达到门槛后自动成为道主，无需夺位。有道主后请走挑战更替。`"
    />
  </el-card>
</template>
