import { useCallback, useEffect, useState } from 'react'
import {
  BackendUnreachableError, fetchBoundaries, fetchCatalogue, fetchHealth, fetchPlaces, withRetry,
} from '../api/client'
import type { Boundaries, Catalogue, Place } from '../api/types'
import { uiStore } from '../state/uiState'

export interface PortalData {
  catalogue: Catalogue
  places: Place[]
  boundaries: Boundaries
}

export type PortalState =
  | { status: 'loading' }
  | { status: 'unreachable' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: PortalData }

/** Everything the portal needs before it can draw: catalogue, places, boundaries. */
export function usePortalData(): { state: PortalState; retry: () => void; refreshCatalogue: () => void } {
  const [state, setState] = useState<PortalState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    // The browser can open before the backend is listening, so allow it a few seconds.
    withRetry(
      () => Promise.all([fetchCatalogue(), fetchPlaces(), fetchBoundaries('province'), fetchBoundaries('district')]),
      4,
      700,
    )
      .then(([catalogue, places, province, district]) => {
        if (cancelled) return
        if (!province || !district) {
          uiStore.getState().addNotice('Boundaries are not loaded, so places cannot be selected on the map.')
          fetchHealth()
            .then((health) => {
              if (!cancelled && health.boundaries_error) {
                uiStore.getState().addNotice(`Boundaries could not be read: ${health.boundaries_error}`)
              }
            })
            .catch(() => undefined)
        }
        const sorted = { ...catalogue, sections: [...catalogue.sections].sort((a, b) => a.order - b.order) }
        setState({ status: 'ready', data: { catalogue: sorted, places, boundaries: { province, district } } })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        if (error instanceof BackendUnreachableError) setState({ status: 'unreachable' })
        else setState({ status: 'error', message: error instanceof Error ? error.message : String(error) })
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  const retry = useCallback(() => setAttempt((n) => n + 1), [])

  /** Fetch the layer list again and swap it in, leaving places and boundaries (and so the map) alone. */
  const refreshCatalogue = useCallback(() => {
    fetchCatalogue()
      .then((catalogue) => {
        const sorted = { ...catalogue, sections: [...catalogue.sections].sort((a, b) => a.order - b.order) }
        setState((current) =>
          current.status === 'ready' ? { status: 'ready', data: { ...current.data, catalogue: sorted } } : current,
        )
      })
      .catch(() => undefined)
  }, [])

  return { state, retry, refreshCatalogue }
}
