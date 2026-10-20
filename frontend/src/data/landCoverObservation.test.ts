import { describe, expect, it } from 'vitest'
import { wantedObservation } from './landCoverObservation'
import type { Catalogue, Layer } from '../api/types'

const annual: Layer = {
  id: 'annual-land-cover',
  section_id: 'land-cover',
  title: 'Annual land classification',
  kind: 'raster',
  status: 'ready',
  legend: null,
  years: { first: 2017, last: 2023, available: [2017, 2018, 2019, 2020, 2021, 2022, 2023] },
  default_opacity: 1,
  tile_source: 'mpc',
}

const local: Layer = {
  id: 'forest',
  section_id: 'land-cover',
  title: 'Forest',
  kind: 'raster',
  status: 'ready',
  legend: null,
  years: { first: 2017, last: 2023 },
  default_opacity: 1,
}

const catalogue: Catalogue = {
  basemap_style_url: 'x',
  sections: [],
  layers: [annual, local],
  forecast: null,
}

describe('wantedObservation', () => {
  it('is nothing when no observation layer is on the map', () => {
    expect(wantedObservation(catalogue, [{ id: 'forest', opacity: 1, hidden: false }], 2020)).toBeNull()
  })

  it('is the layer and the year it shows', () => {
    const wanted = wantedObservation(
      catalogue,
      [{ id: 'annual-land-cover', opacity: 1, hidden: false }],
      2019,
    )
    expect(wanted).toEqual({ layerId: 'annual-land-cover', year: 2019 })
  })

  it('falls back to the latest year when the view has none', () => {
    const wanted = wantedObservation(
      catalogue,
      [{ id: 'annual-land-cover', opacity: 1, hidden: false }],
      null,
    )
    expect(wanted).toEqual({ layerId: 'annual-land-cover', year: 2023 })
  })

  it('clamps a year the layer does not have to the nearest one it does', () => {
    const wanted = wantedObservation(
      catalogue,
      [{ id: 'annual-land-cover', opacity: 1, hidden: false }],
      2030,
    )
    expect(wanted?.year).toBe(2023)
  })

  it('ignores a layer that is not served from the observation', () => {
    const wanted = wantedObservation(catalogue, [{ id: 'forest', opacity: 1, hidden: false }], 2020)
    expect(wanted).toBeNull()
  })
})
