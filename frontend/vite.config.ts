/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rolldownOptions: {
      output: {
        // 第三方库单独分包：业务代码改动时，浏览器可以继续用缓存的库文件
        codeSplitting: {
          groups: [
            { name: 'react', test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/, priority: 3 },
            { name: 'echarts', test: /node_modules[\\/](echarts|zrender|echarts-for-react)[\\/]/, priority: 2 },
            { name: 'vendor', test: /node_modules[\\/]/, priority: 1 },
          ],
        },
      },
    },
    chunkSizeWarningLimit: 900,
  },
  server: {
    port: 3000,
    strictPort: true, // 端口被占用时直接报错，不自动换端口
    proxy: {
      // 开发环境把 /api 转发到 FastAPI，前端代码统一写相对路径
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    // 测试一律走 Mock，不访问后端
    env: { VITE_USE_MOCK: 'true' },
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
