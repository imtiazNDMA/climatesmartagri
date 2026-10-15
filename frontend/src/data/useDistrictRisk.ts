import { useEffect, useState } from 'react'
import { fetchDistrictRisk } from '../api/client'
import type { DistrictRiskResponse } from '../api/types'
import { useView } from '../state/viewState'
import type { ForecastTimesState } from './useForecastTimes'
import type { HazardProductsState } from './useHazardProducts'

export type DistrictRiskState =
  | { status: 'idle' }
  | { status: 'loading'; clear: boolean }
  | { status: 'ready'; data: DistrictRiskResponse }
  | { status: 'error'; message: string }

export function useDistrictRisk(
  active: boolean,
  products: HazardProductsState,
  times: ForecastTimesState,
): DistrictRiskState {
  const choice = useView((state) => state.forecast)
  const product = products.status === 'ready'
    ? products.data.products.find((item) => item.forecast_layer === choice?.layer)
    : undefined
  const slot = times.status === 'ready' ? times.times.find((item) => item.time === choice?.time) : undefined
  const requestKey = active && choice?.time && product && slot
    ? `${product.id}|${choice.layer}|${choice.model}|${choice.level}|${choice.time}|${slot.run}`
    : null
  const choiceKey = active && product && choice
    ? `${product.id}|${choice.layer}|${choice.model}|${choice.level}`
    : null
  const [settled, setSettled] = useState<{
    key: string
    choiceKey: string
    state: Extract<DistrictRiskState, { status: 'ready' | 'error' }>
  } | null>(null)

  useEffect(() => {
    if (!requestKey || !choice?.time || !product || !slot) return
    let cancelled = false
    fetchDistrictRisk(product.id, choice, choice.time, slot.run)
      .then((data) => {
        if (!cancelled && choiceKey) setSettled({ key: requestKey, choiceKey, state: { status: 'ready', data } })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setSettled({
            key: requestKey,
            choiceKey: choiceKey ?? '',
            state: { status: 'error', message: error instanceof Error ? error.message : String(error) },
          })
        }
      })
    return () => { cancelled = true }
  }, [requestKey, choiceKey, choice, product, slot])

  if (!requestKey) return { status: 'idle' }
  return settled?.key === requestKey
    ? settled.state
    : { status: 'loading', clear: settled?.choiceKey !== choiceKey }
}
