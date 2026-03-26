import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiUrl = env.VITE_API_URL || 'http://localhost:8000'

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
    },
    server: {
      port: 5173,
      open: true,
      proxy: {
        // In local dev without VITE_API_URL, proxy to localhost:8000
        '/api': {
          target: apiUrl,
          changeOrigin: true,
        },
        '/ws': {
          target: apiUrl.replace(/^http/, 'ws'),
          ws: true,
          changeOrigin: true,
        },
      },
    },
  }
})

