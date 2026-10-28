import type { Catalogue, Layer } from '../api/types'
import { effectiveYear } from '../state/selectors'
import type { ActiveLayer } from '../state/viewState'

/** The observation the map needs: the layers served from it, in catalogue order, and for which year. */
export interface WantedObservation {
  layerIds: string[]
  year: number
}

/**
 * The annual observation the map should be showing. Every layer served from it shares one request
 * per year, so which of them are on, or in what order, does not change what is asked for.
 */
export function wantedObservation(
  catalogue: Catalogue,
  layers: ActiveLayer[],
  year: number | null,
): WantedObservation | null {
  const on = new Set(layers.map((active) => active.id))
  const served: Layer[] = catalogue.layers.filter((layer) => layer.tile_source === 'mpc' && on.has(layer.id))
  for (const layer of served) {
    const shown = effectiveYear(layer.years, year)
    if (shown !== null) return { layerIds: served.map((l) => l.id), year: shown }
  }
  return null
}
