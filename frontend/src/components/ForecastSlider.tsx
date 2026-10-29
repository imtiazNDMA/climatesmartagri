import { ChevronLeft, ChevronRight, Pause, Play } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { ForecastTimesState } from '../data/useForecastTimes'
import { formatTime } from '../forecast/choice'
import { uiStore } from '../state/uiState'
import { useView, viewStore } from '../state/viewState'

// How long each time stays on screen while playing, once it has finished blending in.
const STEP_MS = 1300

/** Steps the forecast on the map through the times it is available for. */
export function ForecastSlider({ times }: { times: ForecastTimesState }) {
  const time = useView((s) => s.forecast?.time ?? null)
  const [playing, setPlaying] = useState(false)
  const list = times.status === 'ready' ? times.times.map((t) => t.time) : []
  const count = list.length
  const index = time === null ? -1 : list.indexOf(time)

  useEffect(() => {
    if (count < 2) setPlaying(false)
  }, [count])

  useEffect(() => {
    if (!playing || count < 2) return
    const timer = window.setInterval(() => {
      // Wait for the time on its way to arrive: stepping past it would only show a blank map sooner.
      if (uiStore.getState().forecastLoading) return
      const now = list.indexOf(viewStore.getState().forecast?.time ?? '')
      viewStore.getState().setForecastTime(list[now < 0 || now >= count - 1 ? 0 : now + 1])
    }, STEP_MS)
    return () => window.clearInterval(timer)
    // The list changes identity on every render; its length and ends say whether it is the same list.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, count, list[0], list[count - 1]])

  if (count === 0 || index < 0) return null
  const go = (to: number) => viewStore.getState().setForecastTime(list[Math.min(count - 1, Math.max(0, to))])

  return (
    <div className="forecast-slider" role="group" aria-label="Forecast time">
      <button type="button" aria-label="Earlier time" disabled={index <= 0} onClick={() => go(index - 1)}>
        <ChevronLeft size={16} />
      </button>
      <span>{formatTime(list[0])}</span>
      <input
        type="range" min={0} max={count - 1} step={1} value={index} aria-label="Forecast time"
        aria-valuetext={formatTime(list[index])}
        disabled={count < 2}
        onChange={(event) => go(Number(event.target.value))}
      />
      <span>{formatTime(list[count - 1])}</span>
      <button type="button" aria-label="Later time" disabled={index >= count - 1} onClick={() => go(index + 1)}>
        <ChevronRight size={16} />
      </button>
      <strong>{formatTime(list[index])}</strong>
      <button
        type="button" aria-label={playing ? 'Pause' : 'Play'} disabled={count < 2}
        onClick={() => setPlaying((p) => !p)}
      >
        {playing ? <Pause size={16} /> : <Play size={16} />}
      </button>
    </div>
  )
}
