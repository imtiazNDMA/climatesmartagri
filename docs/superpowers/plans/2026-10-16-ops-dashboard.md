# AI Ops Dashboard Implementation Plan (#33)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An `/ops` page in the portal's React app that shows how the AI is doing, from the token-gated `/api/ops` API:
- evaluation pass rates over time, with the change since the previous run;
- a heatmap of each run's cases by repeat, and a comparison of two runs;
- live traffic, latency and errors;
- each trace's span waterfall;
- a keyboard-driven labelling queue with the judge's calibration.

**Architecture:**
- **Routing:** `main.tsx` renders a lazily loaded `OpsApp` when the path is `/ops`, so the portal's bundle is unchanged. Inside `/ops`, views are chosen by the URL hash (`#/runs`, `#/runs/<id>`, `#/compare?a=&b=`, `#/traces/<id>`, `#/labels`), parsed by a pure function.
- **Data and headlines:** pure modules turn API responses into what is drawn: series, the heatmap matrix, waterfall geometry, and headlines that state the finding. Vitest tests these. Components only render them.
- **Charts:** ECharts with the portal's light and dark ink.
- **Browser tests:** they start the e2e backend with a freshly seeded AI store (`seed_ops_store.py`, from #32) and an ops token.

**Tech Stack:** React 19, TypeScript, ECharts 6 (SVG renderer), Vitest, Playwright. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-16-ai-platform-core-design.md` (AI Ops dashboard: the views table, token handling, empty views; Rollout step 6)

## Global Constraints

- The route is `/ops` in the existing app, chosen in `main.tsx` by path. No router library.
- The token is asked for once, kept in `sessionStorage` under `csa-ops-token`, and sent as `X-Ops-Token`. A 401 clears it and asks again with the message "That token was not accepted."
- Headlines state the finding (e.g. "Golden pass rate fell 16.7 points to 50.0%"). There are no explanatory notes under charts.
- Colours: the portal's CSS tokens (`--ink`, `--muted`, `--line`, `--surface`, `--accent`, `--warning`) and its theme (`data-theme` on `<html>`, saved as `csa-theme`). Chart series use the portal's `SLOT_COLOURS`. Pass and fail are shown by colour *and* text or symbol. Dark mode reads at 4.5:1 or better.
- An empty view shows the command that fills it: `npm run eval:live` for evaluation, the live portal for traces, and `npm run eval:live` then `label_answers.py` for labels.
- Times are shown in UTC as `16 Oct 09:00 UTC`.
- The evaluation chart draws live runs only. Recorded replays appear in the runs table, marked "recorded".
- Every view works by keyboard. The labelling view takes `y`/`n` for faithful, `1`–`5` for helpful, and `Enter` to save.
- No new dependencies. Logic tests are Vitest in `src/**/*.test.ts` (node environment). Browser tests are Playwright in `e2e/`.

## Review Focus

1. **The token stops working mid-session** (rotated on the server). Expect the next request's 401 to bring back the token form with "That token was not accepted.", not an error page. Test in Task 3.
2. **No evaluation runs, traces or labels yet** (a fresh install). Expect each view to say how to fill it, not to show empty charts or `NaN%`. Tests in Task 2 and Task 5.
3. **A trace whose spans all start at the same millisecond, or have zero duration.** Expect the waterfall to draw every bar with a minimum width and no `NaN`. Test in Task 1.
4. **A run where every case passed, or none did.** Expect the comparison headline to read sensibly ("No regressions, 2 fixes ...", "No changes ..."), with no "0 regressions" phrasing that looks like a count to act on. Test in Task 1.
5. **The labelling keys while typing a note.** Expect `y`, `n` and the digits to type into the note field, not to change the label. Test in Task 6.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `frontend/src/ops/types.ts` | API response types |
| `frontend/src/ops/route.ts` | `OpsRoute`, `parseRoute`, `routeHash` |
| `frontend/src/ops/format.ts` | `percent`, `seconds`, `utcTime`, `plural` |
| `frontend/src/ops/model.ts` | `GATING`, `passRateSeries`, `heatmap`, `firstFailure`, `waterfall`, headlines, `kpis` |
| `frontend/src/ops/charts.ts` | `passRateOption`, `requestsOption` (ECharts options) |
| `frontend/src/ops/api.ts` | `savedToken`, `saveToken`, `opsApi(token)` |
| `frontend/src/ops/OpsChart.tsx` | ECharts wrapper |
| `frontend/src/ops/useLoad.ts` | load-state hook |
| `frontend/src/ops/OpsApp.tsx` | token gate, theme, navigation, view switch |
| `frontend/src/ops/views/Overview.tsx`, `Runs.tsx`, `Traces.tsx`, `Labels.tsx` | the views |
| `frontend/src/main.tsx` | path switch |
| `frontend/src/styles.css` | `.ops-*` styles |
| `backend/scripts/seed_ops_store.py` | `--replace` |
| `frontend/playwright.config.ts`, `frontend/e2e/ops.spec.ts` | seeded backend with a token; browser tests |

---

### Task 0: Branch and the plan

- [ ] **Step 1: Branch from #32**

```bash
git switch -c feat/33-ops-dashboard feat/32-ops-api
cp ../plans-pending/2026-10-16-ops-dashboard.md docs/superpowers/plans/
git add docs/superpowers/plans/2026-10-16-ops-dashboard.md
git commit -m "docs: implementation plan for the AI Ops dashboard (#33)"
```

- [ ] **Step 2: Confirm the suites are green**

Run: `uv run pytest -q` and `npm --prefix frontend test`
Expected: all pass.

---

### Task 1: Types, routes, formatting and the dashboard's model

**Files:**
- Create: `frontend/src/ops/types.ts`, `frontend/src/ops/route.ts`, `frontend/src/ops/format.ts`, `frontend/src/ops/model.ts`
- Test: `frontend/src/ops/model.test.ts`

**Interfaces:**
- Produces:
  - Types in `types.ts`: `Window`, `Score`, `JudgeSummary`, `RunSummary`, `EvalRun`, `EvalResult`, `HistoryPoint`, `LatestRun`, `Calibration`, `LiveMetrics`, `Metrics`, `TraceSummary`, `Span`, `Trace`, `Comparison`, `QueueItem`.
  - `route.ts`: `OpsRoute` (union over views `overview | runs | run | compare | traces | trace | labels`), `parseRoute(hash: string): OpsRoute`, `routeHash(route: OpsRoute): string`.
  - `format.ts`: `percent(value, digits = 1)`, `seconds(ms)`, `utcTime(iso)`, `plural(count, word, many = word + 's')`.
  - `model.ts`:
    - `GATING: string[]` (the 7 deterministic scorers then `faithfulness`, `helpfulness`)
    - `passRateSeries(history) -> { dataset: string; points: [string, number][] }[]` (live runs only)
    - `heatmap(results) -> { cases: string[]; repeats: number; cells: (boolean | null)[][] }`
    - `firstFailure(scores) -> string | null`
    - `waterfall(spans) -> WaterfallBar[]`, where `WaterfallBar = { id, name, kind, status, depth, offset, width, label }` and offset and width are percentages
    - `evalHeadline(latest)`, `compareHeadline(comparison)`, `trafficHeadline(live, window)`
    - `kpis(metrics) -> Kpi[]`, where `Kpi = { id, label, value, change: string | null, tone: 'good' | 'bad' | 'neutral' }`
    - `selectLabel(run, runs) -> string`: the run's checkbox label, naming its mode only when the same dataset and commit have more than one run

- [ ] **Step 1: Write the failing tests**

`frontend/src/ops/model.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { percent, plural, seconds, utcTime } from './format'
import { compareHeadline, evalHeadline, firstFailure, heatmap, kpis, passRateSeries, selectLabel, trafficHeadline, waterfall } from './model'
import { parseRoute, routeHash } from './route'
import type { Comparison, EvalResult, EvalRun, HistoryPoint, LatestRun, LiveMetrics, Metrics, Span } from './types'

const point = (run_id: string, dataset: string, mode: string, started_at: string, pass_rate: number): HistoryPoint => ({
  run_id, dataset, mode, model: 'qwen', judge_model: null, git_sha: 'abc1234', started_at, status: 'complete',
  pass_rate, scorers: {}, judge: null,
})
const latest = (dataset: string, pass_rate: number, previous_pass_rate: number | null): LatestRun => ({
  ...point(`run-${dataset}`, dataset, 'live', '2026-10-15T12:00:00+00:00', pass_rate), previous_pass_rate,
})
const live = (over: Partial<LiveMetrics> = {}): LiveMetrics => ({
  requests: 4, errors: 1, error_rate: 0.25, p50_latency_ms: 9000, p95_latency_ms: 30000, input_tokens: 1800,
  output_tokens: 180, by_day: [], error_reasons: [], tools: [], ...over,
})

describe('routes', () => {
  it('reads every view from the hash and writes it back', () => {
    const routes = ['#/overview', '#/runs', '#/runs/abc', '#/compare?a=one&b=two', '#/traces', '#/traces/t1', '#/labels']
    for (const hash of routes) expect(routeHash(parseRoute(hash))).toBe(hash)
    expect(parseRoute('')).toEqual({ view: 'overview' })
    expect(parseRoute('#/compare?a=one')).toEqual({ view: 'runs' })
    expect(parseRoute('#/runs/a%2Fb')).toEqual({ view: 'run', id: 'a/b' })
  })
})

describe('format', () => {
  it('formats rates, durations, UTC times and counts', () => {
    expect([percent(0.5), percent(2 / 3), percent(null)]).toEqual(['50.0%', '66.7%', '–'])
    expect([seconds(8000), seconds(null)]).toEqual(['8.0 s', '–'])
    expect(utcTime('2026-10-16T09:05:00+00:00')).toBe('16 Oct 09:05 UTC')
    expect([plural(1, 'regression'), plural(2, 'fix', 'fixes'), plural(0, 'label')]).toEqual(['1 regression', '2 fixes', '0 labels'])
  })
})

describe('evaluation model', () => {
  it('draws one series per dataset from live runs only, in time order', () => {
    const series = passRateSeries([
      point('a', 'golden', 'live', '2026-10-14T12:00:00+00:00', 2 / 3),
      point('c', 'adversarial', 'live', '2026-10-15T12:00:00+00:00', 1),
      point('b', 'golden', 'live', '2026-10-15T12:00:00+00:00', 0.5),
      point('r', 'golden', 'recorded', '2026-10-16T11:00:00+00:00', 0.5),
    ])
    expect(series).toEqual([
      { dataset: 'adversarial', points: [['2026-10-15T12:00:00+00:00', 1]] },
      { dataset: 'golden', points: [['2026-10-14T12:00:00+00:00', 2 / 3], ['2026-10-15T12:00:00+00:00', 0.5]] },
    ])
  })

  it('lays results out as cases by repeats', () => {
    const result = (case_id: string, repeat: number, passed: boolean): EvalResult =>
      ({ id: `${case_id}${repeat}`, run_id: 'r', case_id, repeat, trace_id: null, passed, scores: {} })
    expect(heatmap([result('b', 0, true), result('b', 1, false), result('a', 0, true)])).toEqual({
      cases: ['b', 'a'], repeats: 2, cells: [[true, false], [true, null]],
    })
  })

  it('names the first gating score that failed, judge scores included', () => {
    expect(firstFailure({
      safety: { value: 1, passed: true, reason: 'safe' },
      required_terms: { value: 0.5, passed: false, reason: 'missing: Punjab' },
      latency: { value: 9, passed: null, reason: '9.00 s' },
    })).toBe('required_terms: missing: Punjab')
    expect(firstFailure({ faithfulness: { value: 0, passed: false, reason: 'unfaithful: x' } })).toBe('faithfulness: unfaithful: x')
    expect(firstFailure({ safety: { value: 1, passed: true, reason: 'safe' } })).toBeNull()
  })

  it('states how the main pass rate moved', () => {
    expect(evalHeadline([latest('golden', 0.5, 2 / 3), latest('adversarial', 1, null)])).toBe('Golden pass rate fell 16.7 points to 50.0%')
    expect(evalHeadline([latest('golden', 0.75, 0.5)])).toBe('Golden pass rate rose 25.0 points to 75.0%')
    expect(evalHeadline([latest('golden', 0.5, 0.5)])).toBe('Golden pass rate held at 50.0%')
    expect(evalHeadline([latest('adversarial', 1, null)])).toBe('Adversarial passes 100.0% of cases every repeat')
    expect(evalHeadline([])).toBe('No evaluation runs yet')
  })

  it('states a comparison without counting what did not change', () => {
    const base = { a: { git_sha: 'aaa1111' }, b: { git_sha: 'bbb2222' }, still_failing: [], new_cases: [], removed_cases: [] }
    const compare = (regressions: string[], fixes: string[]) => ({ ...base, regressions, fixes }) as unknown as Comparison
    expect(compareHeadline(compare(['case-b'], ['case-c']))).toBe('1 regression and 1 fix from aaa1111 to bbb2222')
    expect(compareHeadline(compare([], ['x', 'y']))).toBe('No regressions and 2 fixes from aaa1111 to bbb2222')
    expect(compareHeadline(compare(['x', 'y'], []))).toBe('2 regressions from aaa1111 to bbb2222')
    expect(compareHeadline(compare([], []))).toBe('No changes from aaa1111 to bbb2222')
  })
})

describe('traffic model', () => {
  it('states traffic for the window, or that there was none', () => {
    expect(trafficHeadline(live(), '24h')).toBe('4 questions in the last 24 hours, 25.0% failed')
    expect(trafficHeadline(live({ requests: 1, errors: 0, error_rate: 0 }), '7d')).toBe('1 question in the last 7 days, none failed')
    expect(trafficHeadline(live({ requests: 0, errors: 0, error_rate: null }), '30d')).toBe('No questions in the last 30 days')
  })

  it('lays spans out by their start and length, with a minimum width', () => {
    const span = (id: string, parent_id: string | null, kind: Span['kind'], at: string, duration_ms: number): Span => ({
      id, trace_id: 't', parent_id, kind, name: id, started_at: at, duration_ms, status: 'ok', attributes: {},
    })
    const bars = waterfall([
      span('agent', null, 'agent', '2026-10-16T09:00:00.000+00:00', 1000),
      span('llm', 'agent', 'llm', '2026-10-16T09:00:00.250+00:00', 500),
      span('tool', 'agent', 'tool', '2026-10-16T09:00:00.750+00:00', 0),
    ])
    expect(bars.map((b) => [b.id, b.depth, b.offset, b.width])).toEqual([
      ['agent', 0, 0, 100], ['llm', 1, 25, 50], ['tool', 1, 75, 0.5],
    ])
    expect(bars[1].label).toBe('0.50 s')
    const flat = waterfall([span('a', null, 'agent', '2026-10-16T09:00:00+00:00', 0), span('b', 'a', 'tool', '2026-10-16T09:00:00+00:00', 0)])
    expect(flat.map((b) => [b.offset, b.width])).toEqual([[0, 0.5], [0, 0.5]])
    expect(waterfall([])).toEqual([])
  })
})

describe('run selection', () => {
  it('names a run by dataset and commit, adding its mode only when that alone is ambiguous', () => {
    const run = (id: string, dataset: string, git_sha: string, mode: string) => ({ id, dataset, git_sha, mode }) as EvalRun
    const runs = [run('a', 'golden', 'aaa1111', 'live'), run('b', 'golden', 'bbb2222', 'live'), run('r', 'golden', 'bbb2222', 'recorded')]
    expect(runs.map((r) => selectLabel(r, runs))).toEqual([
      'Select golden run aaa1111', 'Select golden run bbb2222 (live)', 'Select golden run bbb2222 (recorded)',
    ])
  })
})

describe('key figures', () => {
  it('shows each dataset, the judge, latency and errors, with their change and tone', () => {
    const metrics = {
      window: '24h', since: '', live: live(),
      eval: { latest: [latest('golden', 0.5, 2 / 3)], history: [] },
      calibration: [{ judge_model: 'gemma', labels: 1, kappa: null, calibrated: false, confusion: {} }],
    } as unknown as Metrics
    metrics.eval.latest[0].judge = { model: 'gemma', calibrated: false, faithful_rate: 2 / 3, mean_helpfulness: null, unavailable: 1 }
    const tiles = kpis(metrics)
    expect(tiles.map((t) => [t.label, t.value, t.change, t.tone])).toEqual([
      ['Golden pass^k', '50.0%', '−16.7 pts', 'bad'],
      ['Judge faithfulness (uncalibrated)', '66.7%', null, 'neutral'],
      ['p95 latency', '30.0 s', null, 'neutral'],
      ['Error rate', '25.0%', null, 'bad'],
      ['Questions', '4', null, 'neutral'],
    ])
  })
})
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `npm --prefix frontend test -- src/ops/model.test.ts`
Expected: FAIL with `Failed to resolve import "./format"`.

- [ ] **Step 3: Types**

`frontend/src/ops/types.ts`:

```ts
/** What the AI Ops API (/api/ops) returns. Times are ISO 8601 with a UTC offset. */

export type Window = '24h' | '7d' | '30d'

export interface Score { value: number | null; passed: boolean | null; reason: string }

export interface JudgeSummary {
  model: string
  calibrated: boolean
  faithful_rate: number | null
  mean_helpfulness: number | null
  unavailable: number
}

export interface RunSummary {
  cases: number
  repeats: number
  passed_cases: number
  pass_rate: number
  flaky_cases: string[]
  scorers: Record<string, number>
  mean_latency_seconds?: number | null
  p95_latency_seconds?: number | null
  judge?: JudgeSummary
}

export interface EvalRun {
  id: string
  dataset: string
  dataset_version: number
  mode: string
  model: string
  judge_model: string | null
  git_sha: string
  started_at: string
  finished_at: string
  repeats: number
  status: string
  summary: RunSummary
}

export interface EvalResult {
  id: string
  run_id: string
  case_id: string
  repeat: number
  trace_id: string | null
  passed: boolean
  scores: Record<string, Score>
}

export interface HistoryPoint {
  run_id: string
  dataset: string
  mode: string
  model: string
  judge_model: string | null
  git_sha: string
  started_at: string
  status: string
  pass_rate: number | null
  scorers: Record<string, number>
  judge: JudgeSummary | null
}

export interface LatestRun extends HistoryPoint { previous_pass_rate: number | null }

export interface Calibration {
  judge_model: string
  labels: number
  kappa: number | null
  calibrated: boolean
  confusion: Record<string, number>
}

export interface LiveMetrics {
  requests: number
  errors: number
  error_rate: number | null
  p50_latency_ms: number | null
  p95_latency_ms: number | null
  input_tokens: number | null
  output_tokens: number | null
  by_day: { day: string; requests: number; errors: number }[]
  error_reasons: { reason: string; count: number }[]
  tools: { tool: string; calls: number; errors: number }[]
}

export interface Metrics {
  window: Window
  since: string
  live: LiveMetrics
  eval: { latest: LatestRun[]; history: HistoryPoint[] }
  calibration: Calibration[]
}

export interface TraceSummary {
  id: string
  source: 'live' | 'eval'
  agent: string
  model: string
  started_at: string
  duration_ms: number
  status: 'ok' | 'error'
  error_reason: string | null
  input_tokens: number | null
  output_tokens: number | null
  eval_run_id: string | null
}

export interface Span {
  id: string
  trace_id: string
  parent_id: string | null
  kind: 'agent' | 'llm' | 'tool' | 'workflow'
  name: string
  started_at: string
  duration_ms: number
  status: string
  attributes: Record<string, unknown>
}

export interface Trace extends TraceSummary {
  question_hash: string
  question_text: string | null
  answer_text: string | null
  spans: Span[]
}

export interface Comparison {
  a: EvalRun
  b: EvalRun
  regressions: string[]
  fixes: string[]
  still_failing: string[]
  new_cases: string[]
  removed_cases: string[]
}

export interface QueueItem { result_id: string; run_id: string; case_id: string; question: string; answer: string }
```

- [ ] **Step 4: Routes and formatting**

`frontend/src/ops/route.ts`:

```ts
/** The dashboard's views, kept in the URL hash so each one can be linked to and survives a reload. */
export type OpsRoute =
  | { view: 'overview' }
  | { view: 'runs' }
  | { view: 'run'; id: string }
  | { view: 'compare'; a: string; b: string }
  | { view: 'traces' }
  | { view: 'trace'; id: string }
  | { view: 'labels' }

export function parseRoute(hash: string): OpsRoute {
  const [path, query = ''] = hash.replace(/^#\/?/, '').split('?')
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent)
  const params = new URLSearchParams(query)
  switch (parts[0]) {
    case 'runs':
      return parts[1] ? { view: 'run', id: parts[1] } : { view: 'runs' }
    case 'compare': {
      const a = params.get('a')
      const b = params.get('b')
      return a && b ? { view: 'compare', a, b } : { view: 'runs' }
    }
    case 'traces':
      return parts[1] ? { view: 'trace', id: parts[1] } : { view: 'traces' }
    case 'labels':
      return { view: 'labels' }
    default:
      return { view: 'overview' }
  }
}

export function routeHash(route: OpsRoute): string {
  switch (route.view) {
    case 'run':
      return `#/runs/${encodeURIComponent(route.id)}`
    case 'compare':
      return `#/compare?${new URLSearchParams({ a: route.a, b: route.b })}`
    case 'trace':
      return `#/traces/${encodeURIComponent(route.id)}`
    default:
      return `#/${route.view}`
  }
}
```

`frontend/src/ops/format.ts`:

```ts
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** A share as a percentage, or a dash when there is none. */
export function percent(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? '–' : `${(value * 100).toFixed(digits)}%`
}

export function seconds(ms: number | null | undefined): string {
  return ms === null || ms === undefined ? '–' : `${(ms / 1000).toFixed(1)} s`
}

/** "16 Oct 09:05 UTC": every reader of the dashboard sees the same time. */
export function utcTime(iso: string): string {
  const at = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${at.getUTCDate()} ${MONTHS[at.getUTCMonth()]} ${pad(at.getUTCHours())}:${pad(at.getUTCMinutes())} UTC`
}

export function plural(count: number, word: string, many = `${word}s`): string {
  return `${count} ${count === 1 ? word : many}`
}
```

- [ ] **Step 5: The dashboard's model**

`frontend/src/ops/model.ts`:

```ts
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
```

- [ ] **Step 6: Run the tests**

Run: `npm --prefix frontend test -- src/ops/model.test.ts`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/ops
git commit -m "feat: AI Ops dashboard model: routes, formatting, series, heatmap, waterfall and headlines (#33)"
```

---

### Task 2: The API client, the load hook, the chart wrapper and chart options

**Files:**
- Create: `frontend/src/ops/api.ts`, `frontend/src/ops/useLoad.ts`, `frontend/src/ops/OpsChart.tsx`, `frontend/src/ops/charts.ts`
- Test: `frontend/src/ops/api.test.ts`, `frontend/src/ops/charts.test.ts`

**Interfaces:**
- Consumes: types (Task 1); `ApiError` from `../api/client`; `SLOT_COLOURS` from `../charts/chartOption`.
- Produces:
  - `TOKEN_KEY = 'csa-ops-token'`, `savedToken(): string | null`, `saveToken(token: string | null): void`.
  - `opsApi(token)` with `metrics(window)`, `runs()`, `run(id)`, `compare(a, b)`, `traces(filters)`, `trace(id)`, `queue()`, `label(body)`, `calibration()`. Each rejects with `ApiError` (reason `ops-unauthorized` on 401).
  - `useLoad<T>(load: () => Promise<T>, deps: unknown[]) -> { state: 'loading' | 'ready' | 'error'; data?: T; error?: Error; reload(): void }`.
  - `OpsChart({ option, label, height = 260 })`.
  - `passRateOption(series, dark)`, `requestsOption(byDay, dark)`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/ops/api.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { opsApi } from './api'

function respond(status: number, body: unknown) {
  return vi.fn(async (_url: string, _init?: RequestInit) => new Response(JSON.stringify(body), { status }))
}

afterEach(() => vi.unstubAllGlobals())

describe('ops api', () => {
  it('sends the token with every request and unwraps lists', async () => {
    const fetchMock = respond(200, { runs: [{ id: 'r1' }] })
    vi.stubGlobal('fetch', fetchMock)

    expect(await opsApi('tok').runs()).toEqual([{ id: 'r1' }])
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/ops/eval-runs')
    expect(new Headers(init?.headers).get('X-Ops-Token')).toBe('tok')
  })

  it('builds trace filters without empty values and encodes ids', async () => {
    const fetchMock = respond(200, { traces: [], next: null })
    vi.stubGlobal('fetch', fetchMock)

    await opsApi('tok').traces({ source: 'live', status: undefined, before: '2026|a b' })
    await opsApi('tok').compare('a/1', 'b')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/ops/traces?source=live&before=2026%7Ca+b')
    expect(fetchMock.mock.calls[1][0]).toBe('/api/ops/eval-runs/compare?a=a%2F1&b=b')
  })

  it('posts labels as JSON', async () => {
    const fetchMock = respond(201, { id: 'l1' })
    vi.stubGlobal('fetch', fetchMock)

    await opsApi('tok').label({ result_id: 'r', labeller: 'officer', faithful: true, helpful: 4, note: '' })
    const init = fetchMock.mock.calls[0][1]!
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(JSON.parse(init.body as string)).toEqual({ result_id: 'r', labeller: 'officer', faithful: true, helpful: 4, note: '' })
  })

  it('turns a refused token into an ApiError with its reason', async () => {
    vi.stubGlobal('fetch', respond(401, { detail: { reason: 'ops-unauthorized', message: 'A valid X-Ops-Token header is required' } }))

    const error = await opsApi('bad').metrics('24h').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).reason).toBe('ops-unauthorized')
    expect((error as ApiError).status).toBe(401)
  })
})
```

`frontend/src/ops/charts.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { passRateOption, requestsOption } from './charts'

describe('ops charts', () => {
  it('draws one labelled line per dataset on a 0–100% axis', () => {
    const option = passRateOption([
      { dataset: 'golden', points: [['2026-10-14T12:00:00+00:00', 2 / 3], ['2026-10-15T12:00:00+00:00', 0.5]] },
      { dataset: 'adversarial', points: [['2026-10-15T12:00:00+00:00', 1]] },
    ], false) as { series: { name: string; data: [string, number][] }[]; yAxis: { max: number } }

    expect(option.series.map((s) => s.name)).toEqual(['golden', 'adversarial'])
    expect(option.series[0].data[1]).toEqual(['2026-10-15T12:00:00+00:00', 50])
    expect(option.yAxis.max).toBe(100)
  })

  it('stacks answered and failed questions per day', () => {
    const option = requestsOption([{ day: '2026-10-16', requests: 3, errors: 1 }], true) as {
      xAxis: { data: string[] }; series: { name: string; data: number[] }[]
    }

    expect(option.xAxis.data).toEqual(['16 Oct'])
    expect(option.series.map((s) => [s.name, s.data])).toEqual([['Answered', [2]], ['Failed', [1]]])
  })
})
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `npm --prefix frontend test -- src/ops`
Expected: FAIL with `Failed to resolve import "./api"` and `"./charts"`.

- [ ] **Step 3: The API client**

`frontend/src/ops/api.ts`:

```ts
import { ApiError } from '../api/client'
import type { Calibration, Comparison, EvalResult, EvalRun, Metrics, QueueItem, Trace, TraceSummary, Window } from './types'

export const TOKEN_KEY = 'csa-ops-token'

/** The token for this browser tab; sessionStorage can be unavailable (private windows), so failures are ignored. */
export function savedToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function saveToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token)
    else sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    // Without storage the token lasts until the page reloads.
  }
}

async function request<T>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('X-Ops-Token', token)
  if (init.body) headers.set('Content-Type', 'application/json')
  const response = await fetch(`/api/ops${path}`, { ...init, headers })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = body && typeof body === 'object' ? (body as { detail?: { reason?: unknown; message?: unknown } }).detail : null
    throw new ApiError(
      response.status,
      typeof detail?.reason === 'string' ? detail.reason : null,
      typeof detail?.message === 'string' ? detail.message : `Request failed (${response.status})`,
    )
  }
  return (await response.json()) as T
}

export interface TraceFilters { source?: 'live' | 'eval'; status?: 'ok' | 'error'; before?: string | null }
export interface LabelBody { result_id: string; labeller: string; faithful: boolean; helpful: number | null; note: string }

export function opsApi(token: string) {
  const query = (values: Record<string, string | null | undefined>) => {
    const params = new URLSearchParams()
    for (const [key, value] of Object.entries(values)) if (value) params.set(key, value)
    const text = params.toString()
    return text ? `?${text}` : ''
  }
  return {
    metrics: (window: Window) => request<Metrics>(token, `/metrics?window=${window}`),
    runs: () => request<{ runs: EvalRun[] }>(token, '/eval-runs').then((body) => body.runs),
    run: (id: string) => request<{ run: EvalRun; results: EvalResult[] }>(token, `/eval-runs/${encodeURIComponent(id)}`),
    compare: (a: string, b: string) => request<Comparison>(token, `/eval-runs/compare${query({ a, b })}`),
    traces: (filters: TraceFilters) =>
      request<{ traces: TraceSummary[]; next: string | null }>(token, `/traces${query({ ...filters })}`),
    trace: (id: string) => request<Trace>(token, `/traces/${encodeURIComponent(id)}`),
    queue: () => request<{ queue: QueueItem[] }>(token, '/labels/queue').then((body) => body.queue),
    label: (body: LabelBody) => request<{ id: string }>(token, '/labels', { method: 'POST', body: JSON.stringify(body) }),
    calibration: () => request<{ judges: Calibration[] }>(token, '/calibration').then((body) => body.judges),
  }
}

export type OpsApi = ReturnType<typeof opsApi>
```

- [ ] **Step 4: The load hook and the chart wrapper**

`frontend/src/ops/useLoad.ts`:

```ts
import { useCallback, useEffect, useState } from 'react'

export interface Loaded<T> { state: 'loading' | 'ready' | 'error'; data?: T; error?: Error; reload: () => void }

/** Runs `load` whenever `deps` change; an answer that arrives after a newer request has started is dropped. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]): Loaded<T> {
  const [version, setVersion] = useState(0)
  const [result, setResult] = useState<Omit<Loaded<T>, 'reload'>>({ state: 'loading' })
  const reload = useCallback(() => setVersion((v) => v + 1), [])
  useEffect(() => {
    let current = true
    setResult((previous) => ({ ...previous, state: 'loading' }))
    load().then(
      (data) => current && setResult({ state: 'ready', data }),
      (error: unknown) => current && setResult({ state: 'error', error: error instanceof Error ? error : new Error(String(error)) }),
    )
    return () => {
      current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version])
  return { ...result, reload }
}
```

`frontend/src/ops/OpsChart.tsx`:

```tsx
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { init, use as registerEChartsModules, type ECharts } from 'echarts/core'
import { SVGRenderer } from 'echarts/renderers'
import { useEffect, useRef } from 'react'

registerEChartsModules([LineChart, BarChart, GridComponent, LegendComponent, TooltipComponent, SVGRenderer])

/** One ECharts plot. `label` names it for screen readers; the headline above it states the finding. */
export function OpsChart({ option, label, height = 260 }: { option: Record<string, unknown>; label: string; height?: number }) {
  const plot = useRef<HTMLDivElement>(null)
  const chart = useRef<ECharts | null>(null)

  useEffect(() => {
    if (!plot.current) return
    const instance = init(plot.current, undefined, { renderer: 'svg' })
    chart.current = instance
    const resize = new ResizeObserver(() => instance.resize())
    resize.observe(plot.current)
    return () => {
      resize.disconnect()
      instance.dispose()
      chart.current = null
    }
  }, [])

  useEffect(() => {
    chart.current?.setOption(option, true)
  }, [option])

  return <div ref={plot} className="ops-chart" role="img" aria-label={label} style={{ height }} />
}
```

- [ ] **Step 5: Chart options**

`frontend/src/ops/charts.ts`:

```ts
import { SLOT_COLOURS } from '../charts/chartOption'
import { utcTime } from './format'

// The portal chart inks (chartOption.ts): on the dark card every text colour reads at 4.5:1 or better.
const INK = {
  light: { ink: '#52514e', grid: '#e1e0d9', surface: '#ffffff' },
  dark: { ink: '#d4dbe6', grid: '#2b3a51', surface: '#18243a' },
}
const FONT = "system-ui, 'Segoe UI', sans-serif"
const FAILED = '#e34948'

function base(dark: boolean) {
  const p = dark ? INK.dark : INK.light
  return {
    animationDuration: 600,
    textStyle: { fontFamily: FONT, color: p.ink, fontSize: 13 },
    grid: { left: 8, right: 16, top: 36, bottom: 8, outerBoundsMode: 'same', outerBoundsContain: 'axisLabel' },
    tooltip: { trigger: 'axis', backgroundColor: p.surface, borderColor: p.grid, textStyle: { color: p.ink } },
    legend: { top: 0, left: 0, textStyle: { color: p.ink } },
    palette: p,
  }
}

/** Pass^k over time, one line per dataset, live runs only. */
export function passRateOption(series: { dataset: string; points: [string, number][] }[], dark: boolean): Record<string, unknown> {
  const { palette, ...common } = base(dark)
  return {
    ...common,
    xAxis: { type: 'time', axisLine: { lineStyle: { color: palette.grid } }, axisLabel: { color: palette.ink } },
    yAxis: {
      type: 'value', min: 0, max: 100, axisLabel: { color: palette.ink, formatter: '{value}%' },
      splitLine: { lineStyle: { color: palette.grid } },
    },
    series: series.map((s, i) => ({
      name: s.dataset,
      type: 'line',
      symbolSize: 8,
      lineStyle: { width: 3, color: SLOT_COLOURS[i % SLOT_COLOURS.length] },
      itemStyle: { color: SLOT_COLOURS[i % SLOT_COLOURS.length] },
      data: s.points.map(([at, rate]) => [at, Math.round(rate * 1000) / 10]),
    })),
  }
}

/** Questions per day, answered and failed stacked. */
export function requestsOption(byDay: { day: string; requests: number; errors: number }[], dark: boolean): Record<string, unknown> {
  const { palette, ...common } = base(dark)
  return {
    ...common,
    xAxis: {
      type: 'category', data: byDay.map((d) => utcTime(`${d.day}T00:00:00+00:00`).split(' ').slice(0, 2).join(' ')),
      axisLabel: { color: palette.ink }, axisLine: { lineStyle: { color: palette.grid } },
    },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { color: palette.ink }, splitLine: { lineStyle: { color: palette.grid } } },
    series: [
      { name: 'Answered', type: 'bar', stack: 'q', itemStyle: { color: SLOT_COLOURS[0] }, data: byDay.map((d) => d.requests - d.errors) },
      { name: 'Failed', type: 'bar', stack: 'q', itemStyle: { color: FAILED }, data: byDay.map((d) => d.errors) },
    ],
  }
}
```

- [ ] **Step 6: Run the tests**

Run: `npm --prefix frontend test -- src/ops`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/ops
git commit -m "feat: AI Ops API client, load hook, chart wrapper and chart options (#33)"
```

---

### Task 3: The dashboard shell, the token gate and the path switch

**Files:**
- Create: `frontend/src/ops/OpsApp.tsx`
- Create (placeholders filled in Tasks 4–6): `frontend/src/ops/views/Overview.tsx`, `Runs.tsx`, `Traces.tsx`, `Labels.tsx`
- Modify: `frontend/src/main.tsx`, `frontend/src/styles.css`
- Modify: `backend/scripts/seed_ops_store.py` (`--replace`), `frontend/playwright.config.ts`
- Test: `frontend/e2e/ops.spec.ts`

**Interfaces:**
- Consumes: `opsApi`, `savedToken`, `saveToken` (Task 2); `parseRoute`, `routeHash` (Task 1).
- Produces:
  - `export default function OpsApp()`.
  - Each view gets `ViewProps = { api: OpsApi; dark: boolean; onUnauthorized(): void }` and exports `Overview`, `Runs`, `RunDetail`, `Compare`, `Traces`, `TraceDetail`, `Labels`.
  - The e2e backend runs with a seeded store and `CSA_OPS_TOKEN=e2e-ops-token`.

- [ ] **Step 1: Write the failing browser test**

`frontend/e2e/ops.spec.ts`:

```ts
import { expect, test } from '@playwright/test'

const TOKEN = 'e2e-ops-token'

test('the dashboard asks for its token and says when it is wrong', async ({ page }) => {
  await page.goto('/ops')
  await expect(page.getByRole('heading', { name: 'AI Ops' })).toBeVisible()

  await page.getByLabel('Ops token').fill('wrong')
  await page.getByRole('button', { name: 'Open dashboard' }).click()
  await expect(page.getByRole('alert')).toHaveText('That token was not accepted.')

  await page.getByLabel('Ops token').fill(TOKEN)
  await page.getByRole('button', { name: 'Open dashboard' }).click()
  await expect(page.getByRole('navigation', { name: 'AI Ops views' })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('csa-ops-token'))).toBe(TOKEN)
})

test('a token the server stops accepting brings the form back', async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('csa-ops-token', 'rotated-away'))
  await page.goto('/ops')

  await expect(page.getByRole('alert')).toHaveText('That token was not accepted.')
  await expect(page.getByLabel('Ops token')).toBeVisible()
})

test('the portal itself is unchanged', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'AI Ops' })).toHaveCount(0)
})
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `npm --prefix frontend exec playwright test e2e/ops.spec.ts`
Expected: FAIL: no `AI Ops` heading (the portal renders at `/ops`).

- [ ] **Step 3: A seeded store and a token for the browser tests**

In `backend/scripts/seed_ops_store.py`, add a `--replace` option and use it. Replace

```python
    parser.add_argument("--db", type=Path, required=True, help="a new database file to fill")
    args = parser.parse_args(argv)
    if args.db.exists():
        parser.error(f"{args.db} exists; give a new file")
```

with

```python
    parser.add_argument("--db", type=Path, required=True, help="a new database file to fill")
    parser.add_argument("--replace", action="store_true", help="delete the file (and its WAL files) first")
    args = parser.parse_args(argv)
    if args.replace:
        for suffix in ("", "-wal", "-shm"):
            Path(f"{args.db}{suffix}").unlink(missing_ok=True)
    if args.db.exists():
        parser.error(f"{args.db} exists; give a new file or --replace")
```

In `frontend/playwright.config.ts`:
- add `import os from 'node:os'` beside the other imports;
- add `const opsDb = path.join(os.tmpdir(), 'csa-ops-e2e.db')` and `const OPS_TOKEN = 'e2e-ops-token'` after `fixtures`;
- change the backend server's `command` to

```ts
      command: `uv run python backend/scripts/seed_ops_store.py --db "${opsDb}" --replace && uv run uvicorn csa_portal.main:create_app --factory --app-dir backend --port 8010`,
```

- and replace its `CSA_AI_DB: ''` line and the comment above it with:

```ts
        // A freshly seeded AI store and an ops token, for the AI Ops dashboard tests. It lives in the system's temp
        // folder, so nothing is written to backend/ai.db; the other tests mock the assistant and never write to it.
        CSA_AI_DB: opsDb,
        CSA_OPS_TOKEN: OPS_TOKEN,
```

- [ ] **Step 4: The path switch**

Replace `frontend/src/main.tsx` with:

```tsx
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
```

- [ ] **Step 5: Placeholder views**

Create these four files, so the shell compiles. Tasks 4–6 replace them.

`frontend/src/ops/views/Overview.tsx`:

```tsx
import type { ViewProps } from '../OpsApp'

export function Overview(_props: ViewProps) {
  return null
}
```

`frontend/src/ops/views/Runs.tsx`:

```tsx
import type { ViewProps } from '../OpsApp'

export function Runs(_props: ViewProps) {
  return null
}

export function RunDetail(_props: ViewProps & { id: string }) {
  return null
}

export function Compare(_props: ViewProps & { a: string; b: string }) {
  return null
}
```

`frontend/src/ops/views/Traces.tsx`:

```tsx
import type { ViewProps } from '../OpsApp'

export function Traces(_props: ViewProps) {
  return null
}

export function TraceDetail(_props: ViewProps & { id: string }) {
  return null
}
```

`frontend/src/ops/views/Labels.tsx`:

```tsx
import type { ViewProps } from '../OpsApp'

export function Labels(_props: ViewProps) {
  return null
}
```

- [ ] **Step 6: The shell**

`frontend/src/ops/OpsApp.tsx`:

```tsx
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
```

The second browser test needs a stored token that the server refuses to bring the form back. To do that, give `OpsApp` a check on its first load: in `OpsApp`, after the `api` memo, add:

```tsx
  useEffect(() => {
    if (!api) return
    api.calibration().catch((error: unknown) => {
      if (refused(error)) onUnauthorized()
    })
  }, [api, onUnauthorized])
```

- [ ] **Step 7: The shell's styles**

Append to `frontend/src/styles.css`:

```css
/* AI Ops dashboard (/ops) */
.ops { min-height: 100vh; background: var(--panel-bg); color: var(--ink); font-family: system-ui, 'Segoe UI', sans-serif; }
.ops-header { display: flex; align-items: center; gap: 24px; padding: 14px 24px; background: var(--surface); border-bottom: 1px solid var(--line); flex-wrap: wrap; }
.ops-header h1 { font-size: 22px; margin: 0; }
.ops-header nav { display: flex; gap: 4px; flex-wrap: wrap; }
.ops-header nav a, .ops-back { color: var(--ink); text-decoration: none; padding: 6px 12px; border-radius: 6px; }
.ops-header nav a[aria-current='page'] { background: var(--accent); color: #fff; }
:root[data-theme='dark'] .ops-header nav a[aria-current='page'] { color: #0a1220; }
.ops-header nav a:focus-visible, .ops-back:focus-visible, .ops button:focus-visible, .ops input:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
.ops-back { margin-left: auto; color: var(--muted); }
.ops-main { padding: 24px; display: grid; gap: 20px; max-width: 1400px; margin: 0 auto; }
.ops-card { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 18px 20px; }
.ops-card h2 { font-size: 18px; margin: 0 0 12px; }
.ops-gate { display: grid; place-items: center; }
.ops-token { display: grid; gap: 10px; width: min(360px, 90vw); }
.ops-token input, .ops input[type='text'], .ops textarea { padding: 8px 10px; border: 1px solid var(--line); border-radius: 6px; background: var(--surface); color: var(--ink); font: inherit; }
.ops button { padding: 8px 14px; border: 0; border-radius: 6px; background: var(--accent); color: #fff; font: inherit; cursor: pointer; }
:root[data-theme='dark'] .ops button { color: #0a1220; }
.ops button:disabled { opacity: 0.6; cursor: default; }
.ops-error { color: var(--warning); font-weight: 650; margin: 0; }
.ops-empty { color: var(--muted); }
.ops-empty code { color: var(--ink); background: var(--panel-bg); padding: 2px 6px; border-radius: 4px; }
```

- [ ] **Step 8: Run the browser test and the logic tests**

Run: `npm --prefix frontend exec playwright test e2e/ops.spec.ts` and `npm --prefix frontend test`
Expected: 3 browser PASS; logic tests PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/main.tsx frontend/src/ops frontend/src/styles.css frontend/playwright.config.ts frontend/e2e/ops.spec.ts backend/scripts/seed_ops_store.py
git commit -m "feat: /ops page with a token gate, views by URL hash, and a seeded store for its browser tests (#33)"
```

---

### Task 4: Overview and evaluation runs

**Files:**
- Modify: `frontend/src/ops/views/Overview.tsx`, `frontend/src/ops/views/Runs.tsx`, `frontend/src/styles.css`
- Test: `frontend/e2e/ops.spec.ts` (append)

**Interfaces:**
- Consumes: `useLoad` (Task 2), `OpsChart`, `passRateOption`, `requestsOption`, and the model functions (Task 1); `ViewProps`, `refused` (Task 3).

- [ ] **Step 1: Write the failing browser tests**

Append to `frontend/e2e/ops.spec.ts`:

```ts
test.describe('with the token', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((token) => sessionStorage.setItem('csa-ops-token', token), TOKEN)
  })

  test('the overview states the evaluation and traffic findings', async ({ page }) => {
    await page.goto('/ops')

    await expect(page.getByRole('heading', { name: 'Golden pass rate fell 16.7 points to 50.0%' })).toBeVisible()
    const golden = page.getByRole('group', { name: 'Golden pass^k' })
    await expect(golden).toContainText('50.0%')
    await expect(golden).toContainText('−16.7 pts')
    await expect(page.getByRole('group', { name: 'Judge faithfulness (uncalibrated)' })).toContainText('66.7%')
    await expect(page.getByRole('heading', { name: '4 questions in the last 24 hours, 25.0% failed' })).toBeVisible()
    await expect(page.getByRole('img', { name: 'Pass rate over time' })).toBeVisible()

    await page.getByRole('radio', { name: '7 days' }).check()
    await expect(page.getByRole('heading', { name: '6 questions in the last 7 days, 33.3% failed' })).toBeVisible()
    await expect(page.getByRole('row', { name: /get_section_facts/ })).toContainText('3')
  })

  test('two runs of a dataset can be compared, and a run shows its cases by repeat', async ({ page }) => {
    await page.goto('/ops#/runs')

    const rows = page.getByRole('row').filter({ hasText: 'golden' })
    await expect(rows).toHaveCount(3)
    await page.getByRole('checkbox', { name: 'Select golden run aaa1111' }).check()
    await page.getByRole('checkbox', { name: 'Select golden run bbb2222 (live)' }).check()
    await page.getByRole('button', { name: 'Compare selected' }).click()

    await expect(page.getByRole('heading', { name: '1 regression and 1 fix from aaa1111 to bbb2222' })).toBeVisible()
    await expect(page.getByRole('list', { name: 'Regressions' })).toContainText('case-b')
    await expect(page.getByRole('list', { name: 'New cases' })).toContainText('case-d')

    await page.goto('/ops#/runs')
    await page.getByRole('link', { name: 'golden bbb2222 (live)' }).click()
    await expect(page.getByRole('heading', { name: /golden: 2 of 4 cases passed every repeat/ })).toBeVisible()
    await expect(page.getByRole('cell', { name: 'case-b repeat 1: failed' })).toBeVisible()
    await expect(page.getByRole('row', { name: /case-b/ })).toContainText('required_terms: missing: Punjab')
  })
})
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `npm --prefix frontend exec playwright test e2e/ops.spec.ts`
Expected: the 2 new tests FAIL (placeholders render nothing).

- [ ] **Step 3: The overview**

Replace `frontend/src/ops/views/Overview.tsx` with:

```tsx
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
```

- [ ] **Step 4: Runs, a run, and a comparison**

Replace `frontend/src/ops/views/Runs.tsx` with:

```tsx
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
```


- [ ] **Step 5: Styles for the overview and runs**

Append to `frontend/src/styles.css`:

```css
.ops-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.ops-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 16px; }
.ops-kpi { display: grid; gap: 4px; padding: 12px 14px; border: 1px solid var(--line); border-radius: 8px; border-left-width: 5px; }
.ops-kpi-label { color: var(--muted); font-size: 13px; }
.ops-kpi-value { font-size: 26px; font-weight: 700; }
.ops-kpi-change { font-size: 13px; font-weight: 650; }
.ops-good { border-left-color: #1baf7a; }
.ops-bad { border-left-color: #e34948; }
.ops-neutral { border-left-color: var(--line); }
.ops-window { display: flex; gap: 12px; }
.ops-split { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-top: 12px; }
.ops table { border-collapse: collapse; width: 100%; font-size: 14px; }
.ops caption { text-align: left; font-weight: 650; padding-bottom: 6px; }
.ops th, .ops td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
.ops a { color: var(--accent); }
.ops-facts { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 0 0 12px; }
.ops-facts dt { color: var(--muted); }
.ops-facts dd { margin: 0; }
.ops-scorers td { position: relative; }
.ops-bar { display: inline-block; height: 10px; background: var(--accent); border-radius: 3px; margin-right: 8px; max-width: 60%; vertical-align: middle; }
.ops-cell { text-align: center; font-weight: 700; width: 70px; }
.ops-pass { background: #dcf3e8; color: #0b5d3b; }
.ops-fail { background: #fbe1df; color: #8e1b14; }
:root[data-theme='dark'] .ops-pass { background: #123b2a; color: #9be3c1; }
:root[data-theme='dark'] .ops-fail { background: #4a1a18; color: #ffb3ad; }
.ops-groups { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }
.ops-groups h3 { font-size: 15px; margin: 0 0 6px; }
.ops-groups ul { margin: 0; padding-left: 18px; }
```

- [ ] **Step 6: Run the browser tests**

Run: `npm --prefix frontend exec playwright test e2e/ops.spec.ts`
Expected: 5 PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/ops/views frontend/src/styles.css frontend/e2e/ops.spec.ts
git commit -m "feat: AI Ops overview, evaluation runs, run heatmap and run comparison (#33)"
```

---

### Task 5: Traces and the span waterfall

**Files:**
- Modify: `frontend/src/ops/views/Traces.tsx`, `frontend/src/styles.css`
- Test: `frontend/e2e/ops.spec.ts` (append inside `with the token`)

**Interfaces:**
- Consumes: `api.traces`, `api.trace` (Task 2), `waterfall` (Task 1).

- [ ] **Step 1: Write the failing browser test**

Inside the `test.describe('with the token', ...)` block of `frontend/e2e/ops.spec.ts`, add:

```ts
  test('traces filter, page, and open as a span waterfall', async ({ page }) => {
    await page.goto('/ops#/traces')

    await expect(page.getByRole('heading', { name: '10 traces shown' })).toBeVisible()
    await page.getByLabel('Source').selectOption('live')
    await expect(page.getByRole('heading', { name: '6 traces shown' })).toBeVisible()
    await page.getByLabel('Status').selectOption('error')
    await expect(page.getByRole('row', { name: /tool-limit/ })).toBeVisible()
    await page.getByLabel('Status').selectOption('')

    await page.getByRole('link', { name: /^Open trace/ }).first().click()
    const bars = page.getByTestId('waterfall').locator('[data-span]')
    await expect(bars).toHaveCount(4)
    await expect(bars.first()).toHaveAttribute('aria-label', /agent assistant, 7\.99 s/)
    await expect(page.getByText('Question text not kept for live traces')).toBeVisible()
  })
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `npm --prefix frontend exec playwright test e2e/ops.spec.ts -g "span waterfall"`
Expected: FAIL (placeholder renders nothing).

- [ ] **Step 3: Traces**

Replace `frontend/src/ops/views/Traces.tsx` with:

```tsx
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
  const traces = [...(first.data?.traces ?? []), ...(extra?.traces ?? [])]
  const next = extra ? extra.next : first.data?.next ?? null
  const more = async () => {
    const page = await api.traces({ source: source || undefined, status: status || undefined, before: next })
    setExtra({ traces: [...(extra?.traces ?? []), ...page.traces], next: page.next })
  }

  return (
    <section className="ops-card">
      <div className="ops-row">
        <h2>{first.data ? `${traces.length} traces shown` : 'Loading…'}</h2>
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
      {first.data && !traces.length ? (
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
      {next && <button type="button" onClick={more}>Show more</button>}
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
```

- [ ] **Step 4: Waterfall styles**

Append to `frontend/src/styles.css`:

```css
.ops-filters { display: flex; gap: 16px; }
.ops select { padding: 6px 8px; border: 1px solid var(--line); border-radius: 6px; background: var(--surface); color: var(--ink); font: inherit; }
.ops-answer { white-space: pre-wrap; }
.ops-waterfall { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.ops-waterfall li { display: grid; grid-template-columns: minmax(180px, 26%) 1fr 90px; align-items: center; gap: 12px; }
.ops-span-name { font-size: 14px; overflow-wrap: anywhere; }
.ops-span-track { position: relative; height: 16px; background: var(--panel-bg); border-radius: 4px; }
.ops-span { position: absolute; top: 0; bottom: 0; border-radius: 4px; }
.ops-span-agent { background: #4a3aa7; }
.ops-span-llm { background: #2a78d6; }
.ops-span-tool { background: #1baf7a; }
.ops-span-workflow { background: #eda100; }
.ops-span-error { background: repeating-linear-gradient(45deg, #e34948, #e34948 4px, #b8322f 4px, #b8322f 8px); }
.ops-span-time { font-variant-numeric: tabular-nums; font-size: 13px; color: var(--muted); }
```

- [ ] **Step 5: Run the browser tests**

Run: `npm --prefix frontend exec playwright test e2e/ops.spec.ts`
Expected: 6 PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/ops/views/Traces.tsx frontend/src/styles.css frontend/e2e/ops.spec.ts
git commit -m "feat: AI Ops traces with filters, paging and a span waterfall (#33)"
```

---

### Task 6: The labelling queue

**Files:**
- Modify: `frontend/src/ops/views/Labels.tsx`, `frontend/src/styles.css`
- Test: `frontend/e2e/ops.spec.ts` (append inside `with the token`)

**Interfaces:**
- Consumes: `api.queue`, `api.label`, `api.calibration` (Task 2); `plural` (Task 1).
- Keys: `y`/`n` set faithful, `1`–`5` set helpful, `Enter` saves. All are ignored while the focus is in a text field.

- [ ] **Step 1: Write the failing browser test**

Inside `test.describe('with the token', ...)`, add:

```ts
  test('answers are labelled by keyboard, and typing a note does not change the label', async ({ page }) => {
    await page.goto('/ops#/labels')

    const before = await page.getByRole('group', { name: 'Judge gemma' }).textContent()
    await expect(page.getByText('Answer for case-b')).toBeVisible()
    await page.getByLabel('Your name').fill('E2E officer')
    // Clicking the answer's text moves the focus out of the inputs, so the keys are shortcuts again.
    await page.getByText('Answer for case-b').click()
    await page.keyboard.press('n')
    await page.keyboard.press('2')
    await page.getByLabel('Note').fill('yes 5 n')
    await expect(page.getByRole('radio', { name: 'Not faithful' })).toBeChecked()
    await expect(page.getByRole('radio', { name: '2' })).toBeChecked()
    await page.getByRole('button', { name: 'Save label' }).click()

    await expect(page.getByText('Answer for case-c')).toBeVisible()
    await expect(page.getByRole('group', { name: 'Judge gemma' })).not.toHaveText(before ?? '')
  })
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `npm --prefix frontend exec playwright test e2e/ops.spec.ts -g "labelled by keyboard"`
Expected: FAIL.

- [ ] **Step 3: The labelling view**

Replace `frontend/src/ops/views/Labels.tsx` with:

```tsx
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
```

The `typing()` check uses `event.target`: once the focus is off the inputs (the test clicks the answer's text), keys go to the page and change the label. Keys typed into the Note field have the input as their target, so they don't.

- [ ] **Step 4: Labelling styles**

Append to `frontend/src/styles.css`:

```css
.ops-label { display: grid; gap: 10px; max-width: 900px; }
.ops-label h3 { font-size: 14px; color: var(--muted); margin: 6px 0 0; }
.ops-label p { margin: 0; }
.ops-label fieldset { border: 1px solid var(--line); border-radius: 8px; display: flex; gap: 16px; flex-wrap: wrap; padding: 8px 12px; }
.ops-label label { display: inline-flex; align-items: center; gap: 6px; }
```

- [ ] **Step 5: Run every test and the full check**

Run: `npm --prefix frontend exec playwright test e2e/ops.spec.ts`, then `npm run check` and `npm run test:e2e`
Expected: 7 ops browser tests PASS; lint, build and every suite PASS. Then confirm the portal's own bundle didn't take in the dashboard: `ls frontend/dist/assets | grep -i ops` lists a separate `OpsApp-*.js` chunk.

- [ ] **Step 6: Check dark mode by eye**

Run the portal with the demo store (README, #32), open `/ops` in dark mode and look at each view. Text on every card, tile, heatmap cell and table must read at 4.5:1 or better. Fix any that do not in `styles.css` and ledger the fixes.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/ops/views/Labels.tsx frontend/src/styles.css frontend/e2e/ops.spec.ts
git commit -m "feat: AI Ops labelling queue with keyboard labels and judge calibration (#33)"
```

---

### Task 7: README and the pull request

- [ ] **Step 1: README**

In `README.md`, at the end of `## Evaluating the assistant`, add:

```markdown
The AI Ops dashboard is at `/ops` (for example `http://127.0.0.1:9080/ops`). It asks once for `CSA_OPS_TOKEN` and shows:
- evaluation pass rates over time;
- a heatmap of each run's cases by repeat, and a comparison of any two runs of a dataset;
- live traffic, latency, errors and tool use;
- each trace's span waterfall;
- a keyboard-driven labelling queue with the judge's calibration.
```

```bash
git add README.md
git commit -m "docs: the AI Ops dashboard in the README (#33)"
```

- [ ] **Step 2: Push and open the PR**

```bash
git push -u origin feat/33-ops-dashboard
gh pr create --base feat/32-ops-api --title "feat: AI Ops dashboard at /ops" --body "Closes #33
Closes #27

> Stacked on #32's PR. After it merges, change this PR's base to \`feat/portal-data\`.

(Fill in: views, screenshots light and dark, test counts.)

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

- [ ] **Step 3: Wait for CI**

Run: `gh pr checks --watch`
Expected: `quality` and `e2e` pass.
