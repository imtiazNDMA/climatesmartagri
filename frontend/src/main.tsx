import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles.css'

// The AI Ops dashboard is its own page at /ops, loaded only there so the portal's bundle does not grow.
const OpsApp = lazy(() => import('./ops/OpsApp'))
const isOps = /^\/ops\/?$/.test(window.location.pathname)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isOps ? (
      <Suspense fallback={null}>
        <OpsApp />
      </Suspense>
    ) : (
      <App />
    )}
  </StrictMode>,
)
