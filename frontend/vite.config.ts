import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// В разработке запросы /api и /health уходят на локальный backend
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': process.env.API_PROXY_TARGET ?? 'http://localhost:8000',
      '/health': process.env.API_PROXY_TARGET ?? 'http://localhost:8000',
    },
  },
})
