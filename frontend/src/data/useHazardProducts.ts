import { useEffect, useState } from 'react'
import { fetchHazardProducts } from '../api/client'
import type { HazardCatalogue } from '../api/types'

export type HazardProductsState =
  | { status: 'loading' }
  | { status: 'ready'; data: HazardCatalogue }
  | { status: 'error'; message: string }

export function useHazardProducts(active: boolean): HazardProductsState {
  const [state, setState] = useState<HazardProductsState>({ status: 'loading' })
  useEffect(() => {
    if (!active) return
    let cancelled = false
    fetchHazardProducts()
      .then((data) => { if (!cancelled) setState({ status: 'ready', data }) })
      .catch((error: unknown) => {
        if (!cancelled) setState({ status: 'error', message: error instanceof Error ? error.message : String(error) })
      })
    return () => { cancelled = true }
  }, [active])
  return state
}
