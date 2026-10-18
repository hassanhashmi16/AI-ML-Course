import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The API runs separately (uvicorn api.main:app). The dev server proxies the
// API paths so the browser stays same-origin and no CORS setup is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/health': 'http://127.0.0.1:8000',
      '/investigations': 'http://127.0.0.1:8000',
      '/reports': 'http://127.0.0.1:8000',
    },
  },
})
