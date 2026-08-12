<template>
  <div class="layout">
    <aside class="side">
      <div class="side-brand">
        <strong>Project修仙</strong>
        <span>运营后台</span>
      </div>

      <div class="side-nav">
        <el-menu :default-active="active" :default-openeds="openedMenus" router>
          <el-menu-item index="/">总览</el-menu-item>

          <el-sub-menu
            v-for="group in domainGroups"
            :key="group.category_id"
            :index="`cat-${group.category_id}`"
          >
            <template #title>
              <span>{{ group.category_title_zh }}</span>
              <span class="cat-count">{{ groupNavCount(group) }}</span>
            </template>
            <!-- 大道与道主：运营动作置顶（立刻开赛 / 剔除道主） -->
            <el-menu-item
              v-if="group.category_id === 'dao'"
              index="/ops/dao-lords"
            >
              道主运营
            </el-menu-item>
            <el-menu-item
              v-for="d in group.domains"
              :key="d.domain_id"
              :index="`/domains/${d.domain_id}`"
              :disabled="!d.enabled"
            >
              {{ d.title }}
              <el-tag
                v-if="d.risk === 'balance'"
                size="small"
                type="danger"
                style="margin-left: 6px"
              >
                高危
              </el-tag>
            </el-menu-item>
          </el-sub-menu>

          <el-menu-item index="/audit">审计</el-menu-item>
        </el-menu>
      </div>

      <div class="side-foot">
        <div>{{ auth.user?.display_name }}</div>
        <div class="roles">{{ auth.user?.roles?.join(', ') }}</div>
        <el-button size="small" @click="onLogout">退出</el-button>
      </div>
    </aside>
    <main class="main">
      <div class="main-scroll">
        <router-view />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchDomains } from '../api/config'
import type { DomainSummary } from '../types/api'
import { useAdminAuthStore } from '../stores/auth'

interface DomainGroup {
  category_id: string
  category_title_zh: string
  category_order: number
  domains: DomainSummary[]
}

const auth = useAdminAuthStore()
const route = useRoute()
const router = useRouter()
const domains = ref<DomainSummary[]>([])

const active = computed(() => route.path)

const domainGroups = computed((): DomainGroup[] => {
  const map = new Map<string, DomainGroup>()
  for (const d of domains.value) {
    const id = d.category_id || 'misc'
    const title = d.category_title_zh || '其它'
    const order = d.category_order ?? 90
    let group = map.get(id)
    if (!group) {
      group = {
        category_id: id,
        category_title_zh: title,
        category_order: order,
        domains: [],
      }
      map.set(id, group)
    }
    group.domains.push(d)
  }
  return [...map.values()].sort((a, b) => a.category_order - b.category_order)
})

/** 类目下入口数（大道与道主含「道主运营」） */
function groupNavCount(group: DomainGroup): number {
  const extra = group.category_id === 'dao' ? 1 : 0
  return group.domains.length + extra
}

/** 当前路由所在类目默认展开 */
const openedMenus = computed(() => {
  const path = route.path
  if (path.startsWith('/ops/dao-lords')) return ['cat-dao']
  if (path.startsWith('/domains/')) {
    const id = path.split('/')[2]
    const d = domains.value.find((x) => x.domain_id === id)
    if (d?.category_id) return [`cat-${d.category_id}`]
  }
  // 默认展开大道与道主（含道主运营 + 赛会配置）
  return ['cat-dao']
})

onMounted(async () => {
  try {
    const data = await fetchDomains()
    domains.value = data.domains
  } catch {
    domains.value = []
  }
})

function onLogout() {
  auth.logout()
  void router.push({ name: 'login' })
}
</script>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  height: 100vh;
  overflow: hidden;
}
.side {
  background: #16352f;
  color: #edf7f4;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100vh;
  overflow: hidden;
}
.side-brand {
  flex: 0 0 auto;
  padding: 16px 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.side-brand span {
  opacity: 0.7;
  font-size: 12px;
}
.side-nav {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding-bottom: 8px;
}
.side-nav::-webkit-scrollbar {
  width: 6px;
}
.side-nav::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.25);
  border-radius: 3px;
}
:deep(.el-menu) {
  border-right: none;
  background: transparent;
}
:deep(.el-menu-item),
:deep(.el-sub-menu__title) {
  color: #d7ebe6;
}
:deep(.el-menu-item.is-active) {
  background: rgba(255, 255, 255, 0.1) !important;
  color: #fff;
}
:deep(.el-sub-menu .el-menu) {
  background: rgba(0, 0, 0, 0.12);
}
.cat-count {
  margin-left: 8px;
  opacity: 0.55;
  font-size: 12px;
}
.side-foot {
  flex: 0 0 auto;
  padding: 12px 16px 16px;
  font-size: 12px;
  opacity: 0.9;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}
.roles {
  margin: 4px 0 10px;
  opacity: 0.7;
  word-break: break-all;
}
.main {
  min-height: 0;
  height: 100vh;
  overflow: hidden;
  background: #f4f7f6;
}
.main-scroll {
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 24px 28px 40px;
}
.main-scroll::-webkit-scrollbar {
  width: 8px;
}
.main-scroll::-webkit-scrollbar-thumb {
  background: rgba(22, 53, 47, 0.25);
  border-radius: 4px;
}
@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
    height: auto;
    overflow: visible;
  }
  .side {
    height: auto;
    max-height: 42vh;
  }
  .main {
    height: auto;
    overflow: visible;
  }
  .main-scroll {
    height: auto;
    overflow: visible;
  }
}
</style>
