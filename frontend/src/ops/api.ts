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
