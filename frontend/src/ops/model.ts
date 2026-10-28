import { percent, plural, seconds } from './format'
import type { Comparison, EvalResult, EvalRun, HistoryPoint, LatestRun, LiveMetrics, Metrics, Score, Span, Window } from './types'

/** Scores that decide a run, in the order a failure is reported: deterministic first, then the judge. */
export const GATING = [
  'grounded_numbers', 'right_section', 'required_terms', 'answer_kind', 'hazard_disclaimer', 'trajectory', 'safety',
  'faithfulness', 'helpfulness',
]

const WINDOW_WORDS: Record<Window, string> = { '24h': '24 hours', '7d': '7 days', '30d': '30 days' }
const title = (word: string) => word.charAt(0).toUpperCase() + word.slice(1)

export function passRateSeries(history: HistoryPoint[]): { dataset: string; points: [string, number][] }[] {
  const byDataset = new Map<string, [string, number][]>()
  for (const run of history) {
    if (run.mode !== 'live' || run.pass_rate === null) continue
    byDataset.set(run.dataset, [...(byDataset.get(run.dataset) ?? []), [run.started_at, run.pass_rate]])
  }
  return [...byDataset.keys()].sort().map((dataset) => ({
    dataset,
    points: [...byDataset.get(dataset)!].sort((x, y) => x[0].localeCompare(y[0])),
  }))
}

export function heatmap(results: EvalResult[]): { cases: string[]; repeats: number; cells: (boolean | null)[][] } {
  const cases: string[] = []
  let repeats = 0
  for (const result of results) {
    if (!cases.includes(result.case_id)) cases.push(result.case_id)
    repeats = Math.max(repeats, result.repeat + 1)
  }
  const cells = cases.map(() => Array<boolean | null>(repeats).fill(null))
  for (const result of results) cells[cases.indexOf(result.case_id)][result.repeat] = result.passed
  return { cases, repeats, cells }
}

export function firstFailure(scores: Record<string, Score>): string | null {
  const name = GATING.find((n) => scores[n]?.passed === false)
  return name ? `${name}: ${scores[name].reason}` : null
}

export interface WaterfallBar {
  id: string
  name: string
  kind: Span['kind']
  status: string
  depth: number
  offset: number
  width: number
  label: string
}

/** Each span as a bar: where it starts and how long it runs, as shares of the whole trace. */
export function waterfall(spans: Span[]): WaterfallBar[] {
  if (!spans.length) return []
  const starts = spans.map((s) => Date.parse(s.started_at))
  const first = Math.min(...starts)
  const last = Math.max(...spans.map((s, i) => starts[i] + s.duration_ms))
  const total = last - first
  const parents = new Map(spans.map((s) => [s.id, s.parent_id]))
  const depth = (id: string | null): number => {
    let steps = 0
    for (let at = id === null ? null : parents.get(id) ?? null; at !== null; at = parents.get(at) ?? null) steps += 1
    return steps
  }
  return spans.map((span, i) => ({
    id: span.id,
    name: span.name,
    kind: span.kind,
    status: span.status,
    depth: depth(span.id),
    offset: total > 0 ? ((starts[i] - first) / total) * 100 : 0,
    width: total > 0 ? Math.max((span.duration_ms / total) * 100, 0.5) : 0.5,
    label: `${(span.duration_ms / 1000).toFixed(2)} s`,
  }))
}

function main(latest: LatestRun[]): LatestRun | undefined {
  return latest.find((run) => run.dataset === 'golden') ?? latest[0]
}

export function evalHeadline(latest: LatestRun[]): string {
  const run = main(latest)
  if (!run || run.pass_rate === null) return 'No evaluation runs yet'
  const name = title(run.dataset)
  if (run.previous_pass_rate === null) return `${name} passes ${percent(run.pass_rate)} of cases every repeat`
  const points = (run.pass_rate - run.previous_pass_rate) * 100
  if (Math.abs(points) < 0.05) return `${name} pass rate held at ${percent(run.pass_rate)}`
  return `${name} pass rate ${points > 0 ? 'rose' : 'fell'} ${Math.abs(points).toFixed(1)} points to ${percent(run.pass_rate)}`
}

export function compareHeadline(comparison: Comparison): string {
  const span = `from ${comparison.a.git_sha} to ${comparison.b.git_sha}`
  const regressions = comparison.regressions.length
  const fixes = comparison.fixes.length
  if (!regressions && !fixes) return `No changes ${span}`
  const lost = regressions ? plural(regressions, 'regression') : 'No regressions'
  return fixes ? `${lost} and ${plural(fixes, 'fix', 'fixes')} ${span}` : `${lost} ${span}`
}

export function trafficHeadline(live: LiveMetrics, window: Window): string {
  const period = `in the last ${WINDOW_WORDS[window]}`
  if (!live.requests) return `No questions ${period}`
  const failed = live.errors ? `${percent(live.error_rate)} failed` : 'none failed'
  return `${plural(live.requests, 'question')} ${period}, ${failed}`
}

export function selectLabel(run: EvalRun, runs: EvalRun[]): string {
  const twins = runs.filter((r) => r.dataset === run.dataset && r.git_sha === run.git_sha).length > 1
  return `Select ${run.dataset} run ${run.git_sha}${twins ? ` (${run.mode})` : ''}`
}

export interface Kpi { id: string; label: string; value: string; change: string | null; tone: 'good' | 'bad' | 'neutral' }

export function kpis(metrics: Metrics): Kpi[] {
  const tiles: Kpi[] = []
  for (const run of metrics.eval.latest) {
    const points = run.previous_pass_rate === null || run.pass_rate === null ? null : (run.pass_rate - run.previous_pass_rate) * 100
    tiles.push({
      id: `eval-${run.dataset}`,
      label: `${title(run.dataset)} pass^k`,
      value: percent(run.pass_rate),
      change: points === null || Math.abs(points) < 0.05 ? null : `${points > 0 ? '+' : '−'}${Math.abs(points).toFixed(1)} pts`,
      tone: points === null || Math.abs(points) < 0.05 ? 'neutral' : points > 0 ? 'good' : 'bad',
    })
  }
  const judged = metrics.eval.latest.find((run) => run.judge)?.judge
  if (judged) {
    tiles.push({
      id: 'judge',
      label: `Judge faithfulness (${judged.calibrated ? 'calibrated' : 'uncalibrated'})`,
      value: percent(judged.faithful_rate),
      change: null,
      tone: 'neutral',
    })
  }
  const live = metrics.live
  tiles.push(
    { id: 'p95', label: 'p95 latency', value: seconds(live.p95_latency_ms), change: null, tone: 'neutral' },
    { id: 'errors', label: 'Error rate', value: percent(live.error_rate), change: null, tone: live.errors ? 'bad' : 'neutral' },
    { id: 'requests', label: 'Questions', value: String(live.requests), change: null, tone: 'neutral' },
  )
  return tiles
}
