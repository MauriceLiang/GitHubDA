import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api/browser': { target: 'http://127.0.0.1:8501', changeOrigin: true } },
  },
  test: { environment: 'jsdom', environmentOptions: { jsdom: { url: 'http://127.0.0.1:5173' } }, setupFiles: ['./src/test/setup.ts'], include: ['src/**/*.test.ts'], restoreMocks: true },
})
