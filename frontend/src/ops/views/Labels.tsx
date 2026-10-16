import { useEffect, useState } from 'react'
import { refused, type ViewProps } from '../OpsApp'
import { plural } from '../format'
import { useLoad } from '../useLoad'

const NAME_KEY = 'csa-ops-labeller'
const typing = (target: EventTarget | null) =>
  target instanceof HTMLElement && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)
  && !(target instanceof HTMLInputElement && target.type === 'radio')

export function Labels({ api, onUnauthorized }: ViewProps) {
  const [version, setVersion] = useState(0)
  const queue = useLoad(() => api.queue(), [api, version])
  const judges = useLoad(() => api.calibration(), [api, version])
  const [name, setName] = useState(() => localStorage.getItem(NAME_KEY) ?? '')
  const [faithful, setFaithful] = useState<boolean | null>(null)
  const [helpful, setHelpful] = useState<number | null>(null)
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const item = queue.data?.[0]

  useEffect(() => {
    for (const error of [queue.error, judges.error]) if (refused(error)) onUnauthorized()
  }, [queue.error, judges.error, onUnauthorized])

  async function save() {
    if (!item || faithful === null || !name.trim() || saving) return
    setSaving(true)
    setProblem(null)
    try {
      await api.label({ result_id: item.result_id, labeller: name.trim(), faithful, helpful, note: note.trim() })
      localStorage.setItem(NAME_KEY, name.trim())
      setFaithful(null)
      setHelpful(null)
      setNote('')
      setVersion((v) => v + 1)
    } catch (error) {
      if (refused(error)) onUnauthorized()
      else setProblem(error instanceof Error ? error.message : String(error))
    } finally {
      setSaving(false)
    }
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (typing(event.target) || event.ctrlKey || event.metaKey || event.altKey) return
      if (event.key === 'y' || event.key === 'n') setFaithful(event.key === 'y')
      else if (/^[1-5]$/.test(event.key)) setHelpful(Number(event.key))
      else if (event.key === 'Enter') void save()
      else return
      event.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  return (
    <>
      <section className="ops-card">
        <h2>{judges.data?.length ? 'Judge calibration' : 'No judged runs yet'}</h2>
        <div className="ops-kpis">
          {(judges.data ?? []).map((j) => (
            <div key={j.judge_model} role="group" aria-label={`Judge ${j.judge_model}`} className={`ops-kpi ${j.calibrated ? 'ops-good' : 'ops-neutral'}`}>
              <span className="ops-kpi-label">{j.judge_model}</span>
              <span className="ops-kpi-value">{j.kappa === null ? 'κ –' : `κ ${j.kappa.toFixed(2)}`}</span>
              <span className="ops-kpi-change">{plural(j.labels, 'label')}, {j.calibrated ? 'calibrated' : 'uncalibrated (needs 20 labels and κ ≥ 0.6)'}</span>
            </div>
          ))}
        </div>
        {!judges.data?.length && <p className="ops-empty">Run an evaluation with <code>--judge</code> to grade answers.</p>}
      </section>
      <section className="ops-card">
        {queue.state === 'loading' && !queue.data && <p className="ops-empty">Loading…</p>}
        {queue.data && !item && (
          <p className="ops-empty">Nothing to label. Run <code>npm run eval:live</code>, then come back.</p>
        )}
        {item && (
          <form className="ops-label" onSubmit={(e) => { e.preventDefault(); void save() }}>
            <h2>{plural(queue.data!.length, 'answer')} to label · {item.case_id}</h2>
            <h3>Question</h3>
            <p>{item.question}</p>
            <h3>Answer</h3>
            <p className="ops-answer">{item.answer}</p>
            <fieldset>
              <legend>Is every factual claim right? (y / n)</legend>
              <label><input type="radio" name="faithful" checked={faithful === true} onChange={() => setFaithful(true)} /> Faithful</label>
              <label><input type="radio" name="faithful" checked={faithful === false} onChange={() => setFaithful(false)} /> Not faithful</label>
            </fieldset>
            <fieldset>
              <legend>How helpful? (1–5, optional)</legend>
              {[1, 2, 3, 4, 5].map((n) => (
                <label key={n}><input type="radio" name="helpful" checked={helpful === n} onChange={() => setHelpful(n)} /> {n}</label>
              ))}
            </fieldset>
            <label>Note <input type="text" value={note} onChange={(e) => setNote(e.target.value)} /></label>
            <label>Your name <input type="text" value={name} onChange={(e) => setName(e.target.value)} /></label>
            {problem && <p role="alert" className="ops-error">{problem}</p>}
            <button type="submit" disabled={faithful === null || !name.trim() || saving}>Save label</button>
          </form>
        )}
      </section>
    </>
  )
}
