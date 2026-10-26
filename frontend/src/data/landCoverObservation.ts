import type { Catalogue, Layer } from '../api/types'
import { effectiveYear } from '../state/selectors'
import type { ActiveLayer } from '../state/viewState'

/** The observation the map needs: which layer is served from it, and for which year. */
export interface WantedObservation {
  layerId: string
  year: number
}

/**
 * The annual observation the map should be showing: the first layer served from the observation
 * that is on the map, and the year that layer actually shows.
 */
export function wantedObservation(
  catalogue: Catalogue,
  layers: ActiveLayer[],
  year: number | null,
): WantedObservation | null {
  for (const active of layers) {
    const layer: Layer | undefined = catalogue.layers.find((l) => l.id === active.id)
    if (!layer || layer.tile_source !== 'mpc') continue
    const shown = effectiveYear(layer.years, year)
    if (shown === null) continue
    return { layerId: layer.id, year: shown }
  }
  return null
}
