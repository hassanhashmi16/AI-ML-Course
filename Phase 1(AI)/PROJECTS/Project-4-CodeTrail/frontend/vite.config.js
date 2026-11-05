import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Preserve the browser origin: public mode validates Host against APP_ORIGIN.
// Vite's string shorthand changes Host to :8000 and fails that check.
const apiProxy = { target: 'http://127.0.0.1:8000', changeOrigin: false }

// The API runs separately (uvicorn api.main:app). The dev server proxies the
// API paths so the browser stays same-origin and no CORS setup is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    // Vite's default (localhost) bound only IPv6 ::1 on Windows, so
    // http://127.0.0.1:5173 refused connections. Listen on both stacks.
    host: true,
    proxy: {
      '/auth': apiProxy,
      '/health': apiProxy,
      '/investigations': apiProxy,
      '/reports': apiProxy,
    },
  },
})
