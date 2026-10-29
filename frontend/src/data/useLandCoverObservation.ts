import { useEffect, useMemo, useState } from 'react'
import { fetchLandCoverObservation } from '../api/client'
import type { Catalogue, LandCoverObservation } from '../api/types'
import { nextObservation, timeObservations } from '../state/selectors'
import { useUi } from '../state/uiState'
import { emptyView, useView } from '../state/viewState'
import { wantedObservation } from './landCoverObservation'

export interface LandCoverObservationState {
  status: 'idle' | 'loading' | 'ready' | 'error'
  data: LandCoverObservation | null
  message: string
  /** While playing, the observation playback comes to next, once it has arrived; its tiles can load ahead. */
  next?: LandCoverObservation | null
}

const IDLE: LandCoverObservationState = { status: 'idle', data: null, message: '' }

/**
 * The annual land-classification observation the map is drawing.
 *
 * The observation is asked for once the layer is on the map and the year it shows has settled,
 * so the map never shows one year's tiles under another year's label.
 */
export function useLandCoverObservation(catalogue: Catalogue): LandCoverObservationState {
  const layers = useView((s) => s.layers)
  const section = useView((s) => s.section)
  const year = useView((s) => s.year)
  const playing = useUi((s) => s.playing)
  const retryCounts = useUi((s) => s.retryCounts)
  const wanted = wantedObservation(catalogue, layers, year)
  const ahead = playing
    ? wantedObservation(catalogue, layers, nextObservation(timeObservations({ ...emptyView, section, layers }, catalogue), year))
    : null
  const aheadYear = ahead && ahead.year !== wanted?.year ? ahead.year : null
  const [next, setNext] = useState<LandCoverObservation | null>(null)
  // Retrying any of the layers drawn from the observation asks for it again.
  const retry = wanted ? wanted.layerIds.reduce((sum, id) => sum + (retryCounts[id] ?? 0), 0) : 0
  const [state, setState] = useState<LandCoverObservationState>(IDLE)

  useEffect(() => {
    if (!wanted) {
      setState(IDLE)
      return
    }
    let cancelled = false
    setState({ status: 'loading', data: null, message: '' })
    fetchLandCoverObservation(wanted.year, retry)
      .then((data) => {
        // A slow answer for a year the user has moved on from is not the year on screen.
        if (!cancelled && data.year === wanted.year) setState({ status: 'ready', data, message: '' })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        const message = error instanceof Error ? error.message : 'The observation could not be loaded.'
        setState({ status: 'error', data: null, message })
      })
    return () => {
      cancelled = true
    }
  }, [wanted?.year, retry, catalogue])

  // Fetched in advance, so playback can blend into the next year without waiting on the search.
  useEffect(() => {
    setNext(null)
    if (aheadYear === null) return
    let cancelled = false
    fetchLandCoverObservation(aheadYear, retry)
      .then((data) => {
        if (!cancelled && data.year === aheadYear) setNext(data)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [aheadYear, retry])

  return useMemo(() => ({ ...state, next }), [state, next])
}
