import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

const devApiTarget = process.env.VITE_DEV_API_TARGET || 'http://127.0.0.1:8080'
const devWsTarget = process.env.VITE_DEV_WS_TARGET || 'ws://127.0.0.1:8080'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: path.resolve(__dirname, './dist'),
    emptyOutDir: true,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: devApiTarget,
        changeOrigin: true,
      },
      '/auth': {
        target: devApiTarget,
        changeOrigin: true,
      },
      '/ws': {
        target: devWsTarget,
        ws: true,
      },
    },
  },
})
