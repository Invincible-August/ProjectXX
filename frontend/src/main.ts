/**
 * 应用入口：挂载 Pinia、Vue Router、Element Plus；启动时从 Storage 恢复登录令牌。
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './style.css'
import { useAuthStore } from './stores/auth'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(ElementPlus)

// 刷新页面后从 localStorage / sessionStorage 恢复 access / refresh
useAuthStore(pinia).loadFromStorage()

app.mount('#app')
