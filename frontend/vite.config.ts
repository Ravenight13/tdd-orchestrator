import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: '/app/',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/tasks': 'http://localhost:8420',
      '/workers': 'http://localhost:8420',
      '/circuits': 'http://localhost:8420',
      '/events': 'http://localhost:8420',
      '/health': 'http://localhost:8420',
      '/runs': 'http://localhost:8420',
      '/metrics': 'http://localhost:8420',
    },
  },
})
