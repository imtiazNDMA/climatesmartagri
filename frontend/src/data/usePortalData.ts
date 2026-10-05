import { useCallback, useEffect, useState } from 'react'
import { BackendUnreachableError, fetchBoundaries, fetchCatalogue, fetchPlaces } from '../api/client'
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
export function usePortalData(): { state: PortalState; retry: () => void } {
  const [state, setState] = useState<PortalState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    Promise.all([fetchCatalogue(), fetchPlaces(), fetchBoundaries('province'), fetchBoundaries('district')])
      .then(([catalogue, places, province, district]) => {
        if (cancelled) return
        if (!province || !district) {
          uiStore.getState().addNotice('Boundaries are not loaded, so places cannot be selected on the map.')
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
  return { state, retry }
}
