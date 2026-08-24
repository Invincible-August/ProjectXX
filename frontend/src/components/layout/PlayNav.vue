<script setup lang="ts">
/**
 * 玩法页互跳：大厅…商店与账号同一组按钮，尺寸与风格一致。
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

interface NavItem {
  path: string
  label: string
  type?: 'primary' | 'success' | 'warning' | 'danger' | 'info'
  plain?: boolean
}

const allItems: NavItem[] = [
  { path: '/hall', label: '大厅' },
  { path: '/character', label: '角色', type: 'primary', plain: true },
  { path: '/avatar', label: '化身', type: 'warning' },
  { path: '/formation', label: '阵法' },
  { path: '/battle', label: '战斗', type: 'danger' },
  { path: '/workshop', label: '工坊', type: 'warning', plain: true },
  { path: '/cave', label: '洞府', type: 'success' },
  { path: '/sect', label: '宗门', type: 'success', plain: true },
  { path: '/social', label: '社交', type: 'primary' },
  { path: '/shop', label: '商店', type: 'warning', plain: true },
  { path: '/account', label: '账号' },
]

const items = computed(() => {
  if (authStore.hasCharacter) return allItems
  return allItems.filter((item) => item.path === '/account')
})

const currentPath = computed(() => route.path)

function isActive(path: string): boolean {
  if (path === '/hall') {
    return currentPath.value === '/hall' || currentPath.value === '/'
  }
  return currentPath.value === path || currentPath.value.startsWith(`${path}/`)
}

function go(path: string): void {
  if (isActive(path) && currentPath.value === path) return
  void router.push(path)
}
</script>

<template>
  <nav class="play-nav" aria-label="玩法跳转">
    <el-button
      v-for="item in items"
      :key="item.path"
      size="small"
      :type="isActive(item.path) ? item.type || 'primary' : item.type"
      :plain="isActive(item.path) ? false : Boolean(item.plain)"
      @click="go(item.path)"
    >
      {{ item.label }}
    </el-button>
  </nav>
</template>

<style scoped>
.play-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  min-width: 0;
}
</style>
