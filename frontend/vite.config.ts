import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const backend = process.env.CSA_BACKEND_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    // 127.0.0.1 with strictPort, so a port already used by another project fails loudly.
    host: '127.0.0.1',
    port: Number(process.env.CSA_FRONTEND_PORT ?? 5180),
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
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})
