import { useEffect, useRef } from 'react'
import { BackendUnreachableError, fetchHealth } from '../api/client'
import type { Catalogue } from '../api/types'
import { uiStore } from '../state/uiState'

const CHECK_EVERY_MS = 5000

/**
 * Check the backend regularly, so losing it shows a banner even when nothing else is being fetched.
 *
 * It also notices a layer the backend has loaded but this page still lists as not loaded, for
 * example a raster that finished converting after the page opened, and calls `onLayersLoaded`
 * so the page can pick it up without a reload.
 */
export function useBackendWatch(catalogue: Catalogue, onLayersLoaded: () => void): void {
  const latest = useRef(catalogue)
  useEffect(() => {
    latest.current = catalogue
  }, [catalogue])

  useEffect(() => {
    let lastReported = ''
    const timer = window.setInterval(() => {
      fetchHealth()
        .then((health) => {
          uiStore.getState().setBackendLost(false)
          const newlyLoaded = latest.current.layers
            .filter((layer) => layer.kind !== 'boundary' && layer.status !== 'ready' && health.layers?.[layer.id])
            .map((layer) => layer.id)
            .join(',')
          // Report each set of newly loaded layers once, in case the layer list cannot catch up.
          if (newlyLoaded && newlyLoaded !== lastReported) onLayersLoaded()
          lastReported = newlyLoaded
        })
        .catch((error: unknown) => {
          if (error instanceof BackendUnreachableError) uiStore.getState().setBackendLost(true)
        })
    }, CHECK_EVERY_MS)
    return () => window.clearInterval(timer)
  }, [onLayersLoaded])
}
