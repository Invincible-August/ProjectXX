<script setup lang="ts">
/**
 * 玩法页顶栏：玩法标签与账号同一组按钮。
 */
import PlayNav from './layout/PlayNav.vue'
</script>

<template>
  <div class="auth-bar">
    <PlayNav />
  </div>
</template>

<style scoped>
.auth-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  padding: 0.5rem 1rem;
  margin-bottom: 0.5rem;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
}
</style>
