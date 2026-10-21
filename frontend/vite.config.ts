import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks: {
          echarts: ['echarts'],
          vue: ['vue', 'vue-router', 'pinia'],
        },
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api/browser': { target: 'http://127.0.0.1:8501', changeOrigin: true },
    },
  },
})
