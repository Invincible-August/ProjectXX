<script setup lang="ts">
/**
 * 上位克制只读说明（显性设计）；不重算矩阵。
 */
</script>

<template>
  <el-card shadow="never" class="dao-restraint">
    <template #header>
      <el-text tag="b">克制说明（样本）</el-text>
    </template>
    <el-text size="small" type="info">
      战报中的克制行由服务端结算后下发，例如「炎极道 克制 炎道（伤害×1.15）」。
      客户端不做本地克制推演。
    </el-text>
    <ul class="list">
      <li>上位道可克制同系下位道，乘区以服务端配置为准。</li>
      <li>无本命道或未勾选运用时，不触发克制乘区。</li>
      <li>完整 37 道克制满表见后续版本。</li>
    </ul>
  </el-card>
</template>

<style scoped>
.list {
  margin: 0.75rem 0 0;
  padding-left: 1.2rem;
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}
</style>
