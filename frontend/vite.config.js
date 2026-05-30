import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Existing: career DNA report generator (local FastAPI dev)
      '/generate-dna': 'http://127.0.0.1:8000',
      // New: client workspace endpoints — strips /api prefix before forwarding
      '/api/clients': {
        target: 'http://127.0.0.1:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
