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
