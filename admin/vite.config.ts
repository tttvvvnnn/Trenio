import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// В разработке запросы /api уходят на локальный backend. Порт другой, чем у Mini App,
// чтобы обе запускались рядом
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/api': process.env.API_PROXY_TARGET ?? 'http://localhost:8000',
    },
  },
})
