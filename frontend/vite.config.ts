import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发服务器将 /api 代理到本地后端（uvicorn 默认 8000）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
