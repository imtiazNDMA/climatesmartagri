import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const backend = process.env.CSA_BACKEND_URL ?? 'http://127.0.0.1:9988'

export default defineConfig({
  plugins: [react()],
  // MapLibre's worker is an ES module that shares a chunk with the main bundle.
  worker: { format: 'es' },
  server: {
    // 127.0.0.1 with strictPort, so a port already used by another project fails loudly.
    host: '127.0.0.1',
    port: Number(process.env.CSA_FRONTEND_PORT ?? 9080),
    strictPort: true,
    proxy: {
      '/api': {
        target: backend,
        changeOrigin: true,
        // Answer 502 when the backend is down, so the client can tell
        // "backend unreachable" apart from a backend error.
        configure: (proxy) => {
          proxy.on('error', (_err, _req, res) => {
            if ('writeHead' in res && !res.headersSent) {
              res.writeHead(502, { 'Content-Type': 'application/json' })
            }
            res.end(JSON.stringify({ detail: { message: 'Backend unreachable', reason: 'unreachable' } }))
          })
        },
      },
    },
  },
  preview: {
    host: '127.0.0.1',
    port: Number(process.env.CSA_FRONTEND_PORT ?? 9080),
    strictPort: true,
    proxy: {
      '/api': { target: backend, changeOrigin: true },
    },
  },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})
