import { ChevronLeft, ChevronRight, Pause, Play } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { Catalogue } from '../api/types'
import { observationIndex, timeObservations } from '../state/selectors'
import { uiStore, useUi } from '../state/uiState'
import { emptyView, useView, viewStore } from '../state/viewState'

/** How long one observation stays on screen, once the map has drawn it, before the next one takes its place. */
const STEP_MS = 1500
/** The longest playback waits for the map to draw a year, so a layer that never loads cannot stall it. */
const MAX_WAIT_MS = 8000

export function TimeSlider({ catalogue }: { catalogue: Catalogue }) {
  const section = useView((s) => s.section)
  const layers = useView((s) => s.layers)
  const year = useView((s) => s.year)
  const playing = useUi((s) => s.playing)
  const setPlaying = uiStore.getState().setPlaying
  // True while a layer on the map is still drawing the year on show.
  const catchingUp = useUi((s) => Object.keys(s.yearLoading).length > 0)
  const [reducedMotion, setReducedMotion] = useState(false)
  // The control moves through the observations the visible content actually has, so it never
  // asks for a year that was never published.
  const observations = useMemo(
    () => timeObservations({ ...emptyView, section, layers }, catalogue),
    [section, layers, catalogue],
  )

  useEffect(() => {
    const media = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!media) return
    setReducedMotion(media.matches)
    const listener = (event: MediaQueryListEvent) => setReducedMotion(event.matches)
    media.addEventListener('change', listener)
    return () => media.removeEventListener('change', listener)
  }, [])

  const index = observationIndex(observations, year)
  const current = index >= 0 ? observations[index] : null

  useEffect(() => {
    // Nothing left to play through, so the control stops where it stands.
    if (!observations.length) setPlaying(false)
  }, [observations, setPlaying])

  useEffect(() => {
    if (reducedMotion) setPlaying(false)
  }, [reducedMotion, setPlaying])

  // Playback stops with the control.
  useEffect(() => () => setPlaying(false), [setPlaying])

  useEffect(() => {
    if (!playing || !observations.length) return
    // Each year is held for a while once the map has drawn it, so the picture never runs behind the label.
    const timer = window.setTimeout(() => {
      const list = observations
      const at = observationIndex(list, viewStore.getState().year)
      // Playback starts again at the first observation once it reaches the last.
      const next = at + 1 >= list.length ? 0 : at + 1
      viewStore.getState().setYear(list[next])
    }, catchingUp ? MAX_WAIT_MS : STEP_MS)
    return () => window.clearTimeout(timer)
  }, [playing, observations, year, catchingUp])

  if (!observations.length) return null
  const first = observations[0]
  const last = observations[observations.length - 1]
  const goTo = (position: number) => viewStore.getState().setYear(observations[position])

  return (
    <div className="time-slider" role="group" aria-label="Year">
      <button
        type="button"
        aria-label="Previous year"
        disabled={index <= 0}
        onClick={() => goTo(index - 1)}
      >
        <ChevronLeft size={16} />
      </button>
      <span>{first}</span>
      <input
        type="range"
        min={0}
        max={observations.length - 1}
        step={1}
        value={index}
        aria-label="Year"
        aria-valuetext={current === null ? undefined : String(current)}
        onChange={(event) => goTo(Number(event.target.value))}
      />
      <span>{last}</span>
      <button
        type="button"
        aria-label="Next year"
        disabled={index >= observations.length - 1}
        onClick={() => goTo(index + 1)}
      >
        <ChevronRight size={16} />
      </button>
      <strong>{current}</strong>
      <button
        type="button"
        aria-label={playing ? 'Pause' : 'Play'}
        disabled={reducedMotion}
        title={
          reducedMotion
            ? 'Playback is off because your system asks for reduced motion'
            : undefined
        }
        onClick={() => setPlaying(!playing)}
      >
        {playing ? <Pause size={16} /> : <Play size={16} />}
      </button>
    </div>
  )
}
