import { useEffect, useState } from 'react'
import { refused, type ViewProps } from '../OpsApp'
import { percent, utcTime } from '../format'
import { compareHeadline, firstFailure, heatmap, selectLabel } from '../model'
import { routeHash } from '../route'
import type { EvalRun } from '../types'
import { useLoad } from '../useLoad'

function useRefusal(error: Error | undefined, onUnauthorized: () => void) {
  useEffect(() => {
    if (refused(error)) onUnauthorized()
  }, [error, onUnauthorized])
}

const runName = (run: EvalRun) => `${run.dataset} ${run.git_sha}${run.mode === 'live' ? ' (live)' : ' (recorded)'}`

export function Runs({ api, onUnauthorized }: ViewProps) {
  const runs = useLoad(() => api.runs(), [api])
  const [picked, setPicked] = useState<string[]>([])
  useRefusal(runs.error, onUnauthorized)
  if (runs.state === 'error') return <p role="alert" className="ops-error">{runs.error?.message}</p>
  if (!runs.data) return <p className="ops-empty">Loading…</p>
  if (!runs.data.length) {
    return <p className="ops-empty">No evaluation runs yet. Run <code>npm run eval:live</code> to record one.</p>
  }
  const chosen = runs.data.filter((run) => picked.includes(run.id))
  const comparable = chosen.length === 2 && chosen[0].dataset === chosen[1].dataset
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p.slice(-1), id]))
  const compare = () => {
    const [older, newer] = [...chosen].sort((x, y) => x.started_at.localeCompare(y.started_at))
    window.location.hash = routeHash({ view: 'compare', a: older.id, b: newer.id })
  }

  return (
    <section className="ops-card">
      <div className="ops-row">
        <h2>{runs.data.length} evaluation runs</h2>
        <button type="button" disabled={!comparable} onClick={compare}>Compare selected</button>
      </div>
      <table>
        <thead>
          <tr><th>Compare</th><th>Run</th><th>Started</th><th>Model</th><th>Pass^k</th><th>Status</th></tr>
        </thead>
        <tbody>
          {runs.data.map((run) => (
            <tr key={run.id}>
              <td>
                <input type="checkbox" checked={picked.includes(run.id)} onChange={() => toggle(run.id)}
                       aria-label={selectLabel(run, runs.data!)} />
              </td>
              <td><a href={routeHash({ view: 'run', id: run.id })}>{runName(run)}</a></td>
              <td>{utcTime(run.started_at)}</td>
              <td>{run.model}{run.judge_model ? ` · judge ${run.judge_model}` : ''}</td>
              <td>{percent(run.summary.pass_rate)} ({run.summary.passed_cases}/{run.summary.cases})</td>
              <td>{run.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

export function RunDetail({ api, onUnauthorized, id }: ViewProps & { id: string }) {
  const run = useLoad(() => api.run(id), [api, id])
  useRefusal(run.error, onUnauthorized)
  if (run.state === 'error') return <p role="alert" className="ops-error">{run.error?.message}</p>
  if (!run.data) return <p className="ops-empty">Loading…</p>
  const { run: record, results } = run.data
  const grid = heatmap(results)

  return (
    <>
      <section className="ops-card">
        <h2>{record.dataset}: {record.summary.passed_cases} of {record.summary.cases} cases passed every repeat ({percent(record.summary.pass_rate)})</h2>
        <dl className="ops-facts">
          <dt>Model</dt><dd>{record.model}</dd>
          <dt>Commit</dt><dd>{record.git_sha}</dd>
          <dt>Mode</dt><dd>{record.mode}, {record.repeats} {record.repeats === 1 ? 'repeat' : 'repeats'}</dd>
          <dt>Status</dt><dd>{record.status}</dd>
        </dl>
        <table className="ops-scorers">
          <caption>Runs passed, by scorer</caption>
          <tbody>
            {Object.entries(record.summary.scorers).map(([name, rate]) => (
              <tr key={name}><th scope="row">{name}</th><td><span className="ops-bar" style={{ width: `${rate * 100}%` }} />{percent(rate)}</td></tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="ops-card">
        <h2>Cases by repeat</h2>
        <table className="ops-heatmap">
          <thead>
            <tr><th>Case</th>{Array.from({ length: grid.repeats }, (_, i) => <th key={i}>Repeat {i + 1}</th>)}<th>First failure</th></tr>
          </thead>
          <tbody>
            {grid.cases.map((caseId, row) => {
              const failing = results.find((r) => r.case_id === caseId && !r.passed)
              return (
                <tr key={caseId}>
                  <th scope="row">{caseId}</th>
                  {grid.cells[row].map((cell, repeat) => (
                    <td key={repeat} className={cell === null ? 'ops-cell' : cell ? 'ops-cell ops-pass' : 'ops-cell ops-fail'}
                        aria-label={`${caseId} repeat ${repeat + 1}: ${cell === null ? 'not run' : cell ? 'passed' : 'failed'}`}>
                      {cell === null ? '' : cell ? '✓' : '✗'}
                    </td>
                  ))}
                  <td>
                    {failing ? firstFailure(failing.scores) : '–'}
                    {failing?.trace_id && <> · <a href={routeHash({ view: 'trace', id: failing.trace_id })}>trace</a></>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>
    </>
  )
}

export function Compare({ api, onUnauthorized, a, b }: ViewProps & { a: string; b: string }) {
  const diff = useLoad(() => api.compare(a, b), [api, a, b])
  useRefusal(diff.error, onUnauthorized)
  if (diff.state === 'error') return <p role="alert" className="ops-error">{diff.error?.message}</p>
  if (!diff.data) return <p className="ops-empty">Loading…</p>
  const groups: [string, string[]][] = [
    ['Regressions', diff.data.regressions], ['Fixes', diff.data.fixes], ['Still failing', diff.data.still_failing],
    ['New cases', diff.data.new_cases], ['Removed cases', diff.data.removed_cases],
  ]
  return (
    <section className="ops-card">
      <h2>{compareHeadline(diff.data)}</h2>
      <div className="ops-groups">
        {groups.map(([title, cases]) => (
          <div key={title}>
            <h3>{title} ({cases.length})</h3>
            {cases.length ? <ul aria-label={title}>{cases.map((c) => <li key={c}>{c}</li>)}</ul> : <p className="ops-empty">None</p>}
          </div>
        ))}
      </div>
    </section>
  )
}
