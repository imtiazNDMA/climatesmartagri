import { useEffect, useRef, useState } from 'react'
import { ApiError, BackendUnreachableError, fetchForecastTimes, warmForecast } from '../api/client'
import type { ForecastTime } from '../api/types'
import { nearestTime, runOf, timesAhead } from '../forecast/choice'
import { useView, viewStore } from '../state/viewState'

/** How many times past the one on screen are fetched in advance. */
const AHEAD = 2

export type ForecastTimesState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; times: ForecastTime[] }
  | { status: 'error'; reason: string | null; message: string }

/**
 * The times the forecast on the map can be shown for. Once they are known, a forecast whose time is
 * not among them moves to the one closest to now.
 */
export function useForecastTimes(): ForecastTimesState {
  const [state, setState] = useState<ForecastTimesState>({ status: 'idle' })
  const warmed = useRef(new Set<string>())
  const layer = useView((s) => s.forecast?.layer ?? null)
  const model = useView((s) => s.forecast?.model ?? null)
  const level = useView((s) => s.forecast?.level ?? null)

  useEffect(() => {
    if (layer === null || model === null || level === null) return setState({ status: 'idle' })
    let cancelled = false
    setState({ status: 'loading' })
    fetchForecastTimes({ layer, model, level })
      .then((times) => {
        if (cancelled) return
        const current = viewStore.getState().forecast?.time ?? null
        if (current === null || !times.some((t) => t.time === current)) {
          viewStore.getState().setForecastTime(nearestTime(times.map((t) => t.time), new Date()))
        }
        setState({ status: 'ready', times })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        const reason =
          error instanceof ApiError ? error.reason : error instanceof BackendUnreachableError ? 'unreachable' : null
        setState({ status: 'error', reason, message: error instanceof Error ? error.message : String(error) })
      })
    return () => {
      cancelled = true
    }
  }, [layer, model, level])

  // Get the times just ahead of the one on screen ready, so stepping or playing forward finds them waiting.
  const time = useView((s) => s.forecast?.time ?? null)
  useEffect(() => {
    if (state.status !== 'ready' || layer === null || model === null || level === null || time === null) return
    for (const ahead of timesAhead(state.times.map((t) => t.time), time, AHEAD)) {
      const run = runOf(state.times, ahead)
      const key = `${layer}|${model}|${level}|${ahead}|${run}`
      if (run === null || warmed.current.has(key)) continue
      warmed.current.add(key)
      warmForecast({ layer, model, level }, ahead, run)
    }
  }, [state, layer, model, level, time])

  return state
}
