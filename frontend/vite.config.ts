import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// В разработке запросы /api (и WebSocket /api/ws) и /health уходят на локальный backend
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: process.env.API_PROXY_TARGET ?? 'http://localhost:8000', ws: true },
      '/health': process.env.API_PROXY_TARGET ?? 'http://localhost:8000',
    },
  },
})
