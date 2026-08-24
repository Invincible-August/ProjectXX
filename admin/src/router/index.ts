/**
 * 后台路由：登录 + 玩家管理（整改首版）。
 * 旧配置域 / 道主 / 审计路由保留重定向，避免书签 404。
 */
import { createRouter, createWebHistory } from 'vue-router'
import { getAdminToken } from '../api/http'

const router = createRouter({
  // 与 Vite base、后端挂载路径一致：http://host:8000/management/
  history: createWebHistory('/management/'),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      component: () => import('../views/AdminLayout.vue'),
      children: [
        {
          path: '',
          redirect: { name: 'player-accounts' },
        },
        {
          path: 'players/accounts',
          name: 'player-accounts',
          component: () => import('../views/AccountManagementView.vue'),
        },
        {
          path: 'players/characters',
          name: 'player-characters',
          component: () => import('../views/CharacterManagementView.vue'),
        },
        // 旧入口：暂统一回到账号管理（后续按类目重建）
        {
          path: 'ops/dao-lords',
          redirect: { name: 'player-accounts' },
        },
        {
          path: 'domains/:domainId',
          redirect: { name: 'player-accounts' },
        },
        {
          path: 'audit',
          redirect: { name: 'player-accounts' },
        },
      ],
    },
  ],
})

router.beforeEach((to) => {
  if (to.meta.public) return true
  if (!getAdminToken()) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
