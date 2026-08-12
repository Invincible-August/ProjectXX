<script setup lang="ts">
/**
 * 突破结果对话框（成功/失败文案来自服务端 message）。
 */
import type { BreakthroughAttemptResult } from '../types/breakthrough'

defineProps<{
  visible: boolean
  result: BreakthroughAttemptResult | null
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
}>()

function close(): void {
  emit('update:visible', false)
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    title="突破结果"
    width="420px"
    @update:model-value="emit('update:visible', $event)"
  >
    <template v-if="result">
      <el-result
        :icon="result.success ? 'success' : 'warning'"
        :title="result.success ? '突破成功' : '突破失败'"
        :sub-title="result.message"
      />
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="类型">
          {{
            result.advance_type === 'major'
              ? '跨境突破'
              : result.advance_type === 'layer'
                ? '层进阶'
                : result.advance_type
          }}
        </el-descriptions-item>
        <el-descriptions-item label="境界进度变化">{{ result.cultivation_delta }}</el-descriptions-item>
        <el-descriptions-item label="灵石变化">{{ result.spirit_stones_delta }}</el-descriptions-item>
        <el-descriptions-item v-if="result.grade_name" label="品阶">
          {{ result.grade_name }}
        </el-descriptions-item>
        <el-descriptions-item label="当前境界">
          {{ result.character.realm_display }}
        </el-descriptions-item>
        <!-- M5-D12：只渲染服务端 dice，不出客户端随机 -->
        <el-descriptions-item v-if="result.dice" label="修为骰出目">
          {{ result.dice.roll }}（区间 {{ result.dice.lo }}–{{ result.dice.hi }}）
        </el-descriptions-item>
        <el-descriptions-item v-if="result.dice" label="成功阈值">
          {{ result.dice.threshold }}
          <template v-if="result.dice.success_rate != null">
            · 成功率 {{ Math.round(Number(result.dice.success_rate) * 1000) / 10 }}%
          </template>
        </el-descriptions-item>
      </el-descriptions>
    </template>
    <template #footer>
      <el-button type="primary" @click="close">知道了</el-button>
    </template>
  </el-dialog>
</template>
