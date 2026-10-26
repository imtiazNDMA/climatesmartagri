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
