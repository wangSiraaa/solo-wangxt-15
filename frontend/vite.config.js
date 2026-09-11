import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 构建产物直接落到 Django 的 frontend_dist：
//   index.html        → 由后端 spa 视图在 / 返回
//   assets/*          → 由 Django staticfiles 以 /static/ 前缀提供
export default defineConfig({
  plugins: [vue()],
  base: '/static/',
  build: {
    outDir: '../backend/frontend_dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
