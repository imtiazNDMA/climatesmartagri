import react from '@vitejs/plugin-react'
import { createLogger } from 'vite'
import { defineConfig } from 'vitest/config'

const backend = process.env.CSA_BACKEND_URL ?? 'http://127.0.0.1:9988'

// The page polls /api/health while the backend starts, and Vite logs every
// refused request with a stack trace. Say it once per outage instead.
let backendDown = false
const logger = createLogger()
const logError = logger.error
logger.error = (message, options) => {
  const code = (options?.error as { code?: string } | null | undefined)?.code
  if (code === 'ECONNREFUSED' && message.includes('http proxy error')) {
    if (!backendDown) logger.warn(`Backend not answering at ${backend}; waiting for it`, { timestamp: true })
    backendDown = true
    return
  }
  logError(message, options)
}

export default defineConfig({
  customLogger: logger,
  plugins: [react()],
  // MapLibre's worker is an ES module that shares a chunk with the main bundle.
  worker: { format: 'es' },
  server: {
    // All interfaces, so other machines on the same network can reach the portal.
    // strictPort, so a port already used by another project fails loudly.
    host: true,
    port: Number(process.env.CSA_FRONTEND_PORT ?? 9080),
    strictPort: true,
    proxy: {
      '/api': {
        target: backend,
        changeOrigin: true,
        // Answer 502 when the backend is down, so the client can tell
        // "backend unreachable" apart from a backend error.
        configure: (proxy) => {
          proxy.on('proxyRes', () => {
            if (backendDown) logger.info('Backend is answering', { timestamp: true })
            backendDown = false
          })
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
    host: true,
    port: Number(process.env.CSA_FRONTEND_PORT ?? 9080),
    strictPort: true,
    proxy: {
      '/api': { target: backend, changeOrigin: true },
    },
  },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})
