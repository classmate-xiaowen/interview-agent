import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发服务器将 /api 代理到本地后端（uvicorn 默认 8000）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 用 127.0.0.1 而非 localhost，避免 Windows 下 localhost 解析为 IPv6(::1)
      // 而 uvicorn 默认只监听 IPv4，导致代理 ECONNREFUSED → 浏览器收到 500
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
