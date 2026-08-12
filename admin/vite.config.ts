import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * 运营后台 Vite。
 *
 * - 生产 / 同端口：``base=/management/``，由后端 8000 托管 ``admin/dist``
 * - 本地热更新：仍可用 5174，经 proxy 访问 ``/admin`` API
 */
export default defineConfig({
  base: '/management/',
  plugins: [vue()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      // 热更新时与后端同路径约定：浏览器打 /admin → 转发到 uvicorn
      '/admin': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
