/**
 * M0～M7 路由表 + 全局前置守卫。
 *
 * 公开页：登录 / 注册 / 学习页；受保护页：创角 / 大厅 / 玩法页。
 * M5：`/tribulation` `/reincarnation`；M6：`/dao` `/dao-lord`；
 * M7 L1：`/sect`；L2：`/market` `/social`；双修/商店仍占位；
 * 待引渡强引导；`showWorldBar` 顶栏。
 */
import {
  createRouter,
  createWebHistory,
  type RouteLocationNormalized,
  type RouteRecordRaw,
} from 'vue-router'
import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import CreateCharacterView from '../views/CreateCharacterView.vue'
import HallView from '../views/HallView.vue'
import FormationView from '../views/FormationView.vue'
import BattleView from '../views/BattleView.vue'
import AvatarView from '../views/AvatarView.vue'
import WorkshopView from '../views/WorkshopView.vue'
import PetsView from '../views/PetsView.vue'
import TribulationView from '../views/TribulationView.vue'
import ReincarnationView from '../views/ReincarnationView.vue'
import DaoView from '../views/DaoView.vue'
import DaoLordView from '../views/DaoLordView.vue'
import DaoLordArenaView from '../views/DaoLordArenaView.vue'
import SectView from '../views/SectView.vue'
import MarketView from '../views/MarketView.vue'
import SocialView from '../views/SocialView.vue'
import FriendsView from '../views/FriendsView.vue'
import PartyView from '../views/PartyView.vue'
import DualCultivationView from '../views/DualCultivationView.vue'
import ShopView from '../views/ShopView.vue'
import TestPage from '../test/apps.vue'
import { useAuthStore } from '../stores/auth'
import { useCharacterStore } from '../stores/character'
import { resolveSafeRedirect } from '../utils/safeRedirect'

/** 路由 meta：公开页 / 需登录 / 根路径分流 / 世界顶栏 */
declare module 'vue-router' {
  interface RouteMeta {
    /** 无需登录即可访问 */
    public?: boolean
    /** 必须登录 */
    requiresAuth?: boolean
    /** 根路径：按会话分流到大厅/创角或登录 */
    isRoot?: boolean
    /** M5+：显示 WorldClockBar；玩法壳挂载后可连 WS */
    showWorldBar?: boolean
    /** M7 L2+ 占位页标题 */
    placeholderTitle?: string
  }
}

/** 玩法路由（需有角色） */
const PLAY_ROUTE_NAMES = new Set([
  'hall',
  'formation',
  'battle',
  'avatar',
  'workshop',
  'pets',
  'tribulation',
  'reincarnation',
  'dao',
  'dao-lord',
  'sect',
  'market',
  'social',
  'friends',
  'party',
  'dual-cultivation',
  'shop',
])

/** 待引渡时禁止进入的积极玩法（允许 /hall；/dao /sect 只读允许） */
const FERRY_BLOCKED_ROUTES = new Set([
  'battle',
  'formation',
  'workshop',
  'avatar',
  'pets',
  'dao-lord',
  'market',
  'dual-cultivation',
  'shop',
])

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'root',
    // 组件仅作占位；beforeEach 会 replace 到实际目标，避免白屏闪一下登录页
    component: LoginView,
    meta: { isRoot: true },
  },
  {
    path: '/login',
    name: 'login',
    component: LoginView,
    meta: { public: true },
  },
  {
    path: '/register',
    name: 'register',
    component: RegisterView,
    meta: { public: true },
  },
  {
    path: '/create-character',
    name: 'create-character',
    component: CreateCharacterView,
    meta: { requiresAuth: true },
  },
  {
    path: '/hall',
    name: 'hall',
    component: HallView,
    meta: { requiresAuth: true, showWorldBar: true },
  },
  {
    path: '/formation',
    name: 'formation',
    component: FormationView,
    meta: { requiresAuth: true, showWorldBar: true },
  },
  {
    path: '/battle',
    name: 'battle',
    component: BattleView,
    meta: { requiresAuth: true, showWorldBar: true },
  },
  {
    path: '/avatar',
    name: 'avatar',
    component: AvatarView,
    meta: { requiresAuth: true, showWorldBar: true },
  },
  {
    path: '/workshop',
    name: 'workshop',
    component: WorkshopView,
    meta: { requiresAuth: true, showWorldBar: true },
  },
  {
    path: '/pets',
    name: 'pets',
    component: PetsView,
    meta: { requiresAuth: true, showWorldBar: true },
  },
  {
    path: '/tribulation',
    name: 'tribulation',
    component: TribulationView,
    meta: { requiresAuth: true, showWorldBar: true },
  },
  {
    path: '/reincarnation',
    name: 'reincarnation',
    component: ReincarnationView,
    meta: { requiresAuth: true, showWorldBar: true },
  },
  {
    path: '/dao',
    name: 'dao',
    component: DaoView,
    meta: { requiresAuth: true, showWorldBar: true },
  },
  {
    path: '/dao-lord/arena',
    name: 'dao-lord-arena',
    component: DaoLordArenaView,
    meta: { requiresAuth: true, showWorldBar: true },
  },
  {
    path: '/dao-lord',
    name: 'dao-lord',
    component: DaoLordView,
    meta: { requiresAuth: true, showWorldBar: true },
  },
  {
    path: '/sect',
    name: 'sect',
    component: SectView,
    meta: { requiresAuth: true, showWorldBar: true },
  },
  {
    path: '/market',
    name: 'market',
    component: MarketView,
    meta: { requiresAuth: true, showWorldBar: true },
  },
  {
    path: '/social',
    name: 'social',
    component: SocialView,
    meta: { requiresAuth: true, showWorldBar: true },
  },
  {
    path: '/friends',
    name: 'friends',
    component: FriendsView,
    meta: { requiresAuth: true, showWorldBar: true },
  },
  {
    path: '/party',
    name: 'party',
    component: PartyView,
    meta: { requiresAuth: true, showWorldBar: true },
  },
  {
    path: '/dual-cultivation',
    name: 'dual-cultivation',
    component: DualCultivationView,
    meta: { requiresAuth: true, showWorldBar: true },
  },
  {
    path: '/shop',
    name: 'shop',
    component: ShopView,
    meta: { requiresAuth: true, showWorldBar: true },
  },
  // 学习用，非 M0 验收；保持公开以免打断联调
  {
    path: '/test',
    name: 'test',
    component: TestPage,
    meta: { public: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

/**
 * M5/M6：按角色状态分流登录后首页。
 *
 * @param authStore - 鉴权 store
 */
async function homePathAfterAuthResolved(
  authStore: ReturnType<typeof useAuthStore>,
): Promise<string> {
  if (!authStore.hasCharacter) return '/create-character'
  const characterStore = useCharacterStore()
  if (!characterStore.character) {
    try {
      await characterStore.fetchMe()
    } catch {
      return authStore.homePathAfterAuth()
    }
  }
  const status = characterStore.character?.status
  if (status === 'awaiting_ferry') return '/reincarnation?mode=ferry'
  if (status === 'reincarnating') return '/reincarnation?mode=newborn'
  if (status === 'tribulation') return '/tribulation'
  return '/hall'
}

router.beforeEach(async (to: RouteLocationNormalized) => {
  const authStore = useAuthStore()

  // 根路径：有会话 → 大厅/创角/状态分流；无会话 → 登录
  if (to.meta.isRoot) {
    if (authStore.hasStoredTokens()) {
      const ok = await authStore.ensureSession()
      if (ok) {
        const path = await homePathAfterAuthResolved(authStore)
        return { path, replace: true }
      }
    }
    return { name: 'login', replace: true }
  }

  // 需登录的页面
  if (to.meta.requiresAuth) {
    if (!authStore.hasStoredTokens()) {
      return {
        name: 'login',
        query: { redirect: to.fullPath },
        replace: true,
      }
    }
    const ok = await authStore.ensureSession()
    if (!ok) {
      return {
        name: 'login',
        query: { redirect: to.fullPath },
        replace: true,
      }
    }
    if (PLAY_ROUTE_NAMES.has(String(to.name)) && !authStore.hasCharacter) {
      return { name: 'create-character', replace: true }
    }
    if (to.name === 'create-character' && authStore.hasCharacter) {
      const path = await homePathAfterAuthResolved(authStore)
      return { path, replace: true }
    }

    // M5：待引渡 / 新生强引导——积极玩法与大厅均导向轮回页（新生不可进厅）
    if (FERRY_BLOCKED_ROUTES.has(String(to.name)) || to.name === 'hall') {
      const characterStore = useCharacterStore()
      if (!characterStore.character) {
        try {
          await characterStore.fetchMe()
        } catch {
          // 拉取失败不挡导航，由页面自行处理
        }
      }
      const st = characterStore.character?.status
      if (st === 'reincarnating' && to.name !== 'reincarnation') {
        return {
          path: '/reincarnation',
          query: { mode: 'newborn' },
          replace: true,
        }
      }
      if (st === 'awaiting_ferry' && FERRY_BLOCKED_ROUTES.has(String(to.name))) {
        return {
          path: '/reincarnation',
          query: { mode: 'ferry' },
          replace: true,
        }
      }
    }
    return true
  }

  // 已登录访问登录/注册 → 直接进游戏入口，避免重复登录
  if (to.name === 'login' || to.name === 'register') {
    if (authStore.hasStoredTokens()) {
      const sessionOk = await authStore.ensureSession()
      if (sessionOk) {
        const redirect = resolveSafeRedirect(to.query.redirect)
        if (redirect) return { path: redirect, replace: true }
        const path = await homePathAfterAuthResolved(authStore)
        return { path, replace: true }
      }
    }
    return true
  }

  return true
})

export default router
