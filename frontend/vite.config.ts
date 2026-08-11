import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { fileURLToPath, URL } from 'node:url'

// The backend serves the built SPA from the same origin in production, so the
// app never needs a configurable API host. In development the proxy below
// reproduces that single-origin arrangement, which keeps the httpOnly refresh
// cookie working exactly as it will in production.
const BACKEND = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      // ws:true is required or the realtime camera channel silently 404s.
      '/ws': { target: BACKEND, ws: true, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        // Split the heavy, rarely-changing libraries so a code change does not
        // force every client to re-download them. Matters more than usual
        // here: the dashboard is served off a small board over building wifi.
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('antd') || id.includes('@ant-design')) return 'antd'
          if (id.includes('recharts') || id.includes('d3-')) return 'charts'
          if (id.includes('react') || id.includes('scheduler')) return 'vendor'
          return undefined
        },
      },
    },
  },
})
