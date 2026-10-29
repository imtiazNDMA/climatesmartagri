import { useEffect, useRef } from 'react'
import { probeLayer } from '../api/client'
import type { Catalogue } from '../api/types'
import { effectiveYear } from '../state/selectors'
import { uiStore, useUi } from '../state/uiState'
import { useView } from '../state/viewState'

/**
 * Checks that each active layer's tiles can be served, and flags the layer if not.
 * A layer is re-checked when its displayed year changes or the user presses Retry.
 */
export function useLayerProbes(catalogue: Catalogue): void {
  const layers = useView((s) => s.layers)
  const year = useView((s) => s.year)
  const retryCounts = useUi((s) => s.retryCounts)
  const probed = useRef(new Map<string, string>())

  useEffect(() => {
    const ui = uiStore.getState()
    const activeIds = new Set(layers.map((l) => l.id))
    for (const id of [...probed.current.keys()]) {
      if (!activeIds.has(id)) {
        probed.current.delete(id)
        ui.forgetLayer(id)
      }
    }
    for (const active of layers) {
      const layer = catalogue.layers.find((l) => l.id === active.id)
      if (!layer) continue
      const shownYear = effectiveYear(layer.years, year)
      const retry = retryCounts[layer.id] ?? 0
      const key = `${shownYear ?? ''}|${retry}`
      if (probed.current.get(layer.id) === key) continue
      probed.current.set(layer.id, key)
      probeLayer(layer, shownYear, retry).then((ok) => {
        if (probed.current.get(layer.id) !== key) return
        if (ok) uiStore.getState().clearLayerError(layer.id)
        else uiStore.getState().setLayerError(layer.id)
      })
    }
  }, [layers, year, retryCounts, catalogue])
}
