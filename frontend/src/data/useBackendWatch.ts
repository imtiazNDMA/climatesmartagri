import { useEffect } from 'react'
import { BackendUnreachableError, fetchHealth } from '../api/client'
import { uiStore } from '../state/uiState'

const CHECK_EVERY_MS = 5000

/** Check the backend regularly, so losing it shows a banner even when nothing else is being fetched. */
export function useBackendWatch(): void {
  useEffect(() => {
    const timer = window.setInterval(() => {
      fetchHealth()
        .then(() => uiStore.getState().setBackendLost(false))
        .catch((error: unknown) => {
          if (error instanceof BackendUnreachableError) uiStore.getState().setBackendLost(true)
        })
    }, CHECK_EVERY_MS)
    return () => window.clearInterval(timer)
  }, [])
}
