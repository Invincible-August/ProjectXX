<script setup lang="ts">
/**
 * 登录后各玩法页顶栏：仅「账号」入口（资料 / 改密 / 退出在账号页）。
 */
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="auth-bar">
    <el-button size="small" type="primary" plain @click="router.push('/account')">
      账号
    </el-button>
  </div>
</template>

<style scoped>
.auth-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 0.5rem 1rem;
  margin-bottom: 0.5rem;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
}
</style>
