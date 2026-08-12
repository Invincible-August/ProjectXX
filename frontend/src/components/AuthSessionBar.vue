<script setup lang="ts">
/**
 * 登录后页面顶栏：展示当前账号与「退出登录」。
 * 退出时清除令牌与用户态，并跳转登录页。
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

/** 顶栏展示名：优先 display_name，否则邮箱/手机 */
const displayLabel = computed(() => {
  const user = authStore.user
  if (!user) return '未登录'
  return user.display_name || user.email || user.phone || `用户 #${user.id}`
})

/**
 * 清除登录态并返回登录页。
 */
async function onLogout(): Promise<void> {
  authStore.logout()
  await router.replace('/login')
}
</script>

<template>
  <div
    style="
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: 0.75rem 1rem;
      margin-bottom: 1rem;
      border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
    "
  >
    <el-text truncated>{{ displayLabel }}</el-text>
    <el-button type="danger" plain @click="onLogout">退出登录</el-button>
  </div>
</template>
