import { useEffect, useState } from 'react'
import { ApiError, BackendUnreachableError, fetchSectionData } from '../api/client'
import type { Section, SectionData } from '../api/types'
import { uiStore } from '../state/uiState'

export type SectionDataState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: SectionData }
  | { status: 'no-data' }
  | { status: 'coming-soon' }
  | { status: 'error'; message: string }

/** The open section's figures and charts for the selected place and year. */
export function useSectionData(section: Section | null, placeId: string | null, year: number | null): SectionDataState {
  const [state, setState] = useState<SectionDataState>({ status: 'idle' })
  const sectionId = section?.id ?? null
  const sectionStatus = section?.status ?? null

  useEffect(() => {
    if (!sectionId || !sectionStatus) return setState({ status: 'idle' })
    if (sectionStatus !== 'ready') return setState({ status: sectionStatus })
    let cancelled = false
    setState({ status: 'loading' })
    fetchSectionData(sectionId, placeId, year)
      .then((data) => {
        if (cancelled) return
        uiStore.getState().setBackendLost(false)
        setState({ status: 'ready', data })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        if (error instanceof BackendUnreachableError) {
          uiStore.getState().setBackendLost(true)
          setState({ status: 'error', message: error.message })
        } else if (error instanceof ApiError && (error.reason === 'no-data' || error.reason === 'coming-soon')) {
          setState({ status: error.reason })
        } else {
          setState({ status: 'error', message: error instanceof Error ? error.message : String(error) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [sectionId, sectionStatus, placeId, year])

  return state
}
