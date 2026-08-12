/**
 * 后台路由：登录 + 布局下的域编辑 / 审计。
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
          name: 'dashboard',
          component: () => import('../views/DashboardView.vue'),
        },
        {
          path: 'ops/dao-lords',
          name: 'ops-dao-lords',
          component: () => import('../views/DaoLordOpsView.vue'),
        },
        {
          path: 'domains/:domainId',
          name: 'domain',
          component: () => import('../views/DomainEditorView.vue'),
          props: true,
        },
        {
          path: 'audit',
          name: 'audit',
          component: () => import('../views/AuditView.vue'),
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
