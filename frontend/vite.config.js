import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Backend runs on http://localhost:8000 (uvicorn server:app --reload --port 8000)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
