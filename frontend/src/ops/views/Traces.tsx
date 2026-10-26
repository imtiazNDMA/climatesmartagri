import { useEffect, useState } from 'react'
import { refused, type ViewProps } from '../OpsApp'
import { seconds, utcTime } from '../format'
import { waterfall } from '../model'
import { routeHash } from '../route'
import type { TraceSummary } from '../types'
import { useLoad } from '../useLoad'

export function Traces({ api, onUnauthorized }: ViewProps) {
  const [source, setSource] = useState<'' | 'live' | 'eval'>('')
  const [status, setStatus] = useState<'' | 'ok' | 'error'>('')
  const [extra, setExtra] = useState<{ traces: TraceSummary[]; next: string | null } | null>(null)
  const first = useLoad(() => api.traces({ source: source || undefined, status: status || undefined }), [api, source, status])
  useEffect(() => {
    setExtra(null)
  }, [source, status])
  useEffect(() => {
    if (refused(first.error)) onUnauthorized()
  }, [first.error, onUnauthorized])

  if (first.state === 'error') return <p role="alert" className="ops-error">{first.error?.message}</p>
  // While a new filter loads, the old rows are not shown: clicking one would open a trace the filter excludes.
  const ready = first.state === 'ready'
  const traces = [...(first.data?.traces ?? []), ...(extra?.traces ?? [])]
  const next = extra ? extra.next : first.data?.next ?? null
  const more = async () => {
    const page = await api.traces({ source: source || undefined, status: status || undefined, before: next })
    setExtra({ traces: [...(extra?.traces ?? []), ...page.traces], next: page.next })
  }

  return (
    <section className="ops-card">
      <div className="ops-row">
        <h2>{ready ? `${traces.length} traces shown` : 'Loading…'}</h2>
        <div className="ops-filters">
          <label>Source{' '}
            <select value={source} onChange={(e) => setSource(e.target.value as typeof source)}>
              <option value="">All</option><option value="live">Live</option><option value="eval">Evaluation</option>
            </select>
          </label>
          <label>Status{' '}
            <select value={status} onChange={(e) => setStatus(e.target.value as typeof status)}>
              <option value="">All</option><option value="ok">Answered</option><option value="error">Failed</option>
            </select>
          </label>
        </div>
      </div>
      {!ready ? null : !traces.length ? (
        <p className="ops-empty">Questions asked in the portal's AI guide, and evaluation runs, leave traces here.</p>
      ) : (
        <table>
          <thead><tr><th>Started</th><th>Source</th><th>Status</th><th>Duration</th><th>Tokens</th><th>Trace</th></tr></thead>
          <tbody>
            {traces.map((t) => (
              <tr key={t.id}>
                <td>{utcTime(t.started_at)}</td>
                <td>{t.source}</td>
                <td>{t.status === 'ok' ? 'answered' : `failed: ${t.error_reason ?? 'unknown'}`}</td>
                <td>{seconds(t.duration_ms)}</td>
                <td>{t.input_tokens === null ? '–' : `${t.input_tokens} in, ${t.output_tokens ?? 0} out`}</td>
                <td><a href={routeHash({ view: 'trace', id: t.id })} aria-label={`Open trace ${t.id.slice(0, 8)}`}>{t.id.slice(0, 8)}</a></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {ready && next && <button type="button" onClick={more}>Show more</button>}
    </section>
  )
}

export function TraceDetail({ api, onUnauthorized, id }: ViewProps & { id: string }) {
  const trace = useLoad(() => api.trace(id), [api, id])
  useEffect(() => {
    if (refused(trace.error)) onUnauthorized()
  }, [trace.error, onUnauthorized])
  if (trace.state === 'error') return <p role="alert" className="ops-error">{trace.error?.message}</p>
  if (!trace.data) return <p className="ops-empty">Loading…</p>
  const t = trace.data
  const bars = waterfall(t.spans)

  return (
    <>
      <section className="ops-card">
        <h2>{t.status === 'ok' ? 'Answered' : `Failed: ${t.error_reason}`} in {seconds(t.duration_ms)}</h2>
        <dl className="ops-facts">
          <dt>Started</dt><dd>{utcTime(t.started_at)}</dd>
          <dt>Source</dt><dd>{t.source}{t.eval_run_id && <> · <a href={routeHash({ view: 'run', id: t.eval_run_id })}>evaluation run</a></>}</dd>
          <dt>Model</dt><dd>{t.model}</dd>
          <dt>Tokens</dt><dd>{t.input_tokens === null ? '–' : `${t.input_tokens} in, ${t.output_tokens ?? 0} out`}</dd>
        </dl>
        {t.question_text ? (
          <>
            <h3>Question</h3><p>{t.question_text}</p>
            <h3>Answer</h3><p className="ops-answer">{t.answer_text}</p>
          </>
        ) : (
          <p className="ops-empty">Question text not kept for live traces (set <code>CSA_TRACE_CONTENT=1</code> to keep it).</p>
        )}
      </section>
      <section className="ops-card">
        <h2>{bars.length} spans</h2>
        <ol className="ops-waterfall" data-testid="waterfall">
          {bars.map((bar) => (
            <li key={bar.id} data-span={bar.kind} aria-label={`${bar.kind} ${bar.name}, ${bar.label}${bar.status === 'error' ? ', failed' : ''}`}>
              <span className="ops-span-name" style={{ paddingLeft: bar.depth * 16 }}>{bar.kind} · {bar.name}</span>
              <span className="ops-span-track">
                <span className={`ops-span ops-span-${bar.kind}${bar.status === 'error' ? ' ops-span-error' : ''}`}
                      style={{ left: `${bar.offset}%`, width: `${bar.width}%` }} />
              </span>
              <span className="ops-span-time">{bar.label}{bar.status === 'error' ? ' ✗' : ''}</span>
            </li>
          ))}
        </ol>
      </section>
    </>
  )
}
