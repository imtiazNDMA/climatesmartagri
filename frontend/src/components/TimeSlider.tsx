import { ChevronLeft, ChevronRight, Pause, Play } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { Catalogue } from '../api/types'
import { timeRange } from '../state/selectors'
import { emptyView, useView, viewStore } from '../state/viewState'

const STEP_MS = 1000

export function TimeSlider({ catalogue }: { catalogue: Catalogue }) {
  const section = useView((s) => s.section)
  const layers = useView((s) => s.layers)
  const year = useView((s) => s.year)
  const [playing, setPlaying] = useState(false)
  const range = useMemo(() => timeRange({ ...emptyView, section, layers }, catalogue), [section, layers, catalogue])

  const first = range?.first ?? 0
  const last = range?.last ?? 0
  const current = Math.min(last, Math.max(first, year ?? last))

  useEffect(() => {
    if (!range) setPlaying(false)
  }, [range])

  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => {
      const now = viewStore.getState().year ?? last
      viewStore.getState().setYear(now >= last ? first : now + 1)
    }, STEP_MS)
    return () => window.clearInterval(timer)
  }, [playing, first, last])

  if (!range) return null
  const setYear = (value: number) => viewStore.getState().setYear(Math.min(last, Math.max(first, value)))

  return (
    <div className="time-slider" role="group" aria-label="Year">
      <button type="button" aria-label="Previous year" disabled={current <= first} onClick={() => setYear(current - 1)}>
        <ChevronLeft size={16} />
      </button>
      <span>{first}</span>
      <input
        type="range" min={first} max={last} step={1} value={current} aria-label="Year"
        onChange={(event) => setYear(Number(event.target.value))}
      />
      <span>{last}</span>
      <button type="button" aria-label="Next year" disabled={current >= last} onClick={() => setYear(current + 1)}>
        <ChevronRight size={16} />
      </button>
      <strong>{current}</strong>
      <button type="button" aria-label={playing ? 'Pause' : 'Play'} onClick={() => setPlaying((p) => !p)}>
        {playing ? <Pause size={16} /> : <Play size={16} />}
      </button>
    </div>
  )
}
