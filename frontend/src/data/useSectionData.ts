import { useEffect, useRef, useState } from 'react'
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
  /** The section and place whose data was last asked for. */
  const shown = useRef<string | null>(null)

  useEffect(() => {
    if (!sectionId || !sectionStatus) {
      shown.current = null
      return setState({ status: 'idle' })
    }
    if (sectionStatus !== 'ready') {
      shown.current = null
      return setState({ status: sectionStatus })
    }
    let cancelled = false
    // Moving through the years of the same section and place, the figures and charts on screen stay until
    // the new year's arrive: taking them away for a moment would redraw every chart from nothing at each step.
    const same = shown.current === `${sectionId}|${placeId ?? ''}`
    shown.current = `${sectionId}|${placeId ?? ''}`
    setState((before) => (same && before.status === 'ready' ? before : { status: 'loading' }))
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
