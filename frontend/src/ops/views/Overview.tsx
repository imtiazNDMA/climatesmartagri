import { useEffect, useState } from 'react'
import { refused, type ViewProps } from '../OpsApp'
import { OpsChart } from '../OpsChart'
import { passRateOption, requestsOption } from '../charts'
import { evalHeadline, kpis, passRateSeries, trafficHeadline } from '../model'
import type { Window } from '../types'
import { useLoad } from '../useLoad'

const WINDOWS: { id: Window; label: string }[] = [
  { id: '24h', label: '24 hours' }, { id: '7d', label: '7 days' }, { id: '30d', label: '30 days' },
]

export function Overview({ api, dark, onUnauthorized }: ViewProps) {
  const [window, setWindow] = useState<Window>('24h')
  const metrics = useLoad(() => api.metrics(window), [api, window])
  useEffect(() => {
    if (refused(metrics.error)) onUnauthorized()
  }, [metrics.error, onUnauthorized])

  if (metrics.state === 'error') return <p role="alert" className="ops-error">{metrics.error?.message}</p>
  if (!metrics.data) return <p className="ops-empty">Loading…</p>
  const data = metrics.data
  const series = passRateSeries(data.eval.history)

  return (
    <>
      <section className="ops-card">
        <h2>{evalHeadline(data.eval.latest)}</h2>
        <div className="ops-kpis">
          {kpis(data).map((tile) => (
            <div key={tile.id} role="group" aria-label={tile.label} className={`ops-kpi ops-${tile.tone}`}>
              <span className="ops-kpi-label">{tile.label}</span>
              <span className="ops-kpi-value">{tile.value}</span>
              {tile.change && <span className="ops-kpi-change">{tile.change}</span>}
            </div>
          ))}
        </div>
        {series.length ? (
          <OpsChart option={passRateOption(series, dark)} label="Pass rate over time" />
        ) : (
          <p className="ops-empty">No live evaluation runs yet. Run <code>npm run eval:live</code> to record one.</p>
        )}
      </section>
      <section className="ops-card">
        <div className="ops-row">
          <h2>{trafficHeadline(data.live, window)}</h2>
          <div role="radiogroup" aria-label="Window" className="ops-window">
            {WINDOWS.map((w) => (
              <label key={w.id}>
                <input type="radio" name="window" checked={window === w.id} onChange={() => setWindow(w.id)} /> {w.label}
              </label>
            ))}
          </div>
        </div>
        {data.live.requests ? (
          <>
            <OpsChart option={requestsOption(data.live.by_day, dark)} label="Questions per day" height={220} />
            <div className="ops-split">
              <table>
                <caption>Tool calls</caption>
                <thead><tr><th>Tool</th><th>Calls</th><th>Failed</th></tr></thead>
                <tbody>{data.live.tools.map((t) => <tr key={t.tool}><td>{t.tool}</td><td>{t.calls}</td><td>{t.errors}</td></tr>)}</tbody>
              </table>
              <table>
                <caption>Why questions failed</caption>
                <thead><tr><th>Reason</th><th>Count</th></tr></thead>
                <tbody>{data.live.error_reasons.map((r) => <tr key={r.reason}><td>{r.reason}</td><td>{r.count}</td></tr>)}</tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="ops-empty">Questions asked in the portal's AI guide appear here.</p>
        )}
      </section>
    </>
  )
}
