import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { opsApi, savedToken, saveToken, type OpsApi } from './api'
import { parseRoute, routeHash, type OpsRoute } from './route'
import { Labels } from './views/Labels'
import { Overview } from './views/Overview'
import { Compare, RunDetail, Runs } from './views/Runs'
import { TraceDetail, Traces } from './views/Traces'

export interface ViewProps { api: OpsApi; dark: boolean; onUnauthorized: () => void }

const NAV: { view: OpsRoute['view']; label: string }[] = [
  { view: 'overview', label: 'Overview' },
  { view: 'runs', label: 'Evaluation runs' },
  { view: 'traces', label: 'Traces' },
  { view: 'labels', label: 'Labelling' },
]
const SECTION: Record<OpsRoute['view'], OpsRoute['view']> = {
  overview: 'overview', runs: 'runs', run: 'runs', compare: 'runs', traces: 'traces', trace: 'traces', labels: 'labels',
}

/** True when an error means the token was refused, so the form should come back. */
export function refused(error: unknown): boolean {
  return error instanceof ApiError && error.reason === 'ops-unauthorized'
}

export default function OpsApp() {
  const [token, setToken] = useState<string | null>(savedToken)
  const [refusedOnce, setRefusedOnce] = useState(false)
  const [route, setRoute] = useState(() => parseRoute(window.location.hash))
  const [dark] = useState(() => {
    const saved = localStorage.getItem('csa-theme')
    return saved ? saved === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light'
    document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
    document.title = 'AI Ops · CSA Portal'
  }, [dark])
  useEffect(() => {
    const onHash = () => setRoute(parseRoute(window.location.hash))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const onUnauthorized = useCallback(() => {
    saveToken(null)
    setToken(null)
    setRefusedOnce(true)
  }, [])
  const api = useMemo(() => (token ? opsApi(token) : null), [token])
  useEffect(() => {
    if (!api) return
    api.calibration().catch((error: unknown) => {
      if (refused(error)) onUnauthorized()
    })
  }, [api, onUnauthorized])

  if (!api) return <TokenForm refused={refusedOnce} onToken={(value) => { saveToken(value); setToken(value) }} />

  const props: ViewProps = { api, dark, onUnauthorized }
  return (
    <div className="ops">
      <header className="ops-header">
        <h1>AI Ops</h1>
        <nav aria-label="AI Ops views">
          {NAV.map((item) => (
            <a key={item.view} href={routeHash({ view: item.view } as OpsRoute)}
               aria-current={SECTION[route.view] === item.view ? 'page' : undefined}>{item.label}</a>
          ))}
        </nav>
        <a className="ops-back" href="/">Back to the portal</a>
      </header>
      <main className="ops-main">
        {route.view === 'overview' && <Overview {...props} />}
        {route.view === 'runs' && <Runs {...props} />}
        {route.view === 'run' && <RunDetail {...props} id={route.id} />}
        {route.view === 'compare' && <Compare {...props} a={route.a} b={route.b} />}
        {route.view === 'traces' && <Traces {...props} />}
        {route.view === 'trace' && <TraceDetail {...props} id={route.id} />}
        {route.view === 'labels' && <Labels {...props} />}
      </main>
    </div>
  )
}

function TokenForm({ refused: wasRefused, onToken }: { refused: boolean; onToken: (token: string) => void }) {
  const [value, setValue] = useState('')
  const [checking, setChecking] = useState(false)
  const [rejected, setRejected] = useState(wasRefused)

  async function submit(event: FormEvent) {
    event.preventDefault()
    const token = value.trim()
    if (!token) return
    setChecking(true)
    try {
      await opsApi(token).calibration()
      onToken(token)
    } catch (error) {
      setRejected(refused(error))
      if (!refused(error)) throw error
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="ops ops-gate">
      <form className="ops-card ops-token" onSubmit={submit}>
        <h1>AI Ops</h1>
        <label htmlFor="ops-token">Ops token</label>
        <input id="ops-token" type="password" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)} autoFocus />
        {rejected && <p role="alert" className="ops-error">That token was not accepted.</p>}
        <button type="submit" disabled={checking}>Open dashboard</button>
      </form>
    </div>
  )
}
