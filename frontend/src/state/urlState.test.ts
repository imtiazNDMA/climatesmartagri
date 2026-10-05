import { describe, expect, it } from 'vitest'
import type { Catalogue, Layer, Place } from '../api/types'
import { parseView, serializeView } from './urlState'
import { emptyView, type View } from './viewState'

const layer = (id: string, patch: Partial<Layer> = {}): Layer => ({
  id, section_id: 'yearly', title: id, kind: 'raster', status: 'ready',
  legend: { type: 'classes', items: [{ colour: '#000', label: id }] },
  years: null, default_opacity: 0.8, ...patch,
})
const catalogue: Catalogue = {
  basemap_style_url: '',
  sections: [
    { id: 'yearly', title: 'Yearly', icon: 'trees', order: 1, status: 'ready', summary: '',
      place_levels: ['national'], years: { first: 2000, last: 2010 } },
    { id: 'static', title: 'Static', icon: 'trees', order: 2, status: 'ready', summary: '',
      place_levels: ['national'], years: null },
  ],
  layers: [
    layer('forest'),
    layer('irrigated', { section_id: 'static' }),
    layer('empty', { status: 'no-data' }),
    layer('provinces', { kind: 'boundary', section_id: null, legend: null }),
  ],
}
const places: Place[] = [
  { id: 'PK', name: 'Pakistan', level: 'national', parent_id: null, bbox: [0, 0, 1, 1] },
  { id: 'PK1', name: 'Alpha', level: 'province', parent_id: 'PK', bbox: [0, 0, 1, 1] },
]
const parse = (search: string) => parseView(search, catalogue, places)

describe('serializeView', () => {
  it('is empty for the empty view', () => {
    expect(serializeView(emptyView)).toBe('')
  })

  it('writes every part in a fixed order', () => {
    const view: View = {
      section: 'yearly',
      full: true,
      layers: [
        { id: 'forest', opacity: 0.8, hidden: true },
        { id: 'irrigated', opacity: 1, hidden: false },
      ],
      place: 'PK1',
      year: 2005,
    }
    expect(serializeView(view)).toBe(
      '?section=yearly&view=charts&layers=forest:0.8,irrigated:1&hidden=forest&place=PK1&year=2005',
    )
    expect(serializeView({ ...view, full: false })).toBe(
      '?section=yearly&layers=forest:0.8,irrigated:1&hidden=forest&place=PK1&year=2005',
    )
  })
})

describe('parseView', () => {
  it('round-trips a full view', () => {
    const view: View = {
      section: 'yearly',
      full: true,
      layers: [
        { id: 'forest', opacity: 0.35, hidden: true },
        { id: 'irrigated', opacity: 1, hidden: false },
      ],
      place: 'PK1',
      year: 2005,
    }
    expect(parse(serializeView(view))).toEqual({ view, dropped: [] })
  })

  it('returns the empty view for an empty query', () => {
    expect(parse('')).toEqual({ view: emptyView, dropped: [] })
  })

  it('drops an unknown section, layer and place, and names them', () => {
    const { view, dropped } = parse('?section=nope&layers=ghost:1,forest:0.5&place=XX')
    expect(view.section).toBeNull()
    expect(view.layers).toEqual([{ id: 'forest', opacity: 0.5, hidden: false }])
    expect(view.place).toBeNull()
    expect(dropped).toEqual(['section "nope"', 'layer "ghost"', 'place "XX"'])
  })

  it('refuses layers that cannot be shown', () => {
    const { view, dropped } = parse('?layers=empty:1,provinces:1')
    expect(view.layers).toEqual([])
    expect(dropped).toEqual(['layer "empty"', 'layer "provinces"'])
  })

  it('handles garbage values without throwing', () => {
    const { view, dropped } = parse('?layers=forest:abc,forest:1,irrigated:5,,&hidden=ghost,forest&year=2015.5')
    expect(view.layers).toEqual([
      { id: 'forest', opacity: 0.8, hidden: true },
      { id: 'irrigated', opacity: 0.8, hidden: false },
    ])
    expect(view.year).toBeNull()
    expect(dropped).toEqual([
      'opacity "abc" for layer "forest"',
      'layer "forest" (repeated)',
      'opacity "5" for layer "irrigated"',
      'hidden layer "ghost"',
      'year "2015.5"',
    ])
  })

  it('uses the default opacity when none is given, without complaint', () => {
    expect(parse('?layers=forest')).toEqual({
      view: { ...emptyView, layers: [{ id: 'forest', opacity: 0.8, hidden: false }] },
      dropped: [],
    })
  })

  it('treats an empty layers parameter as no layers', () => {
    expect(parse('?layers=')).toEqual({ view: emptyView, dropped: [] })
  })

  it('reads the country id as no selection', () => {
    expect(parse('?place=PK')).toEqual({ view: emptyView, dropped: [] })
  })

  it('keeps a year only inside the range of what is on screen', () => {
    expect(parse('?section=yearly&year=2005').view.year).toBe(2005)
    expect(parse('?section=yearly&year=1800')).toEqual({
      view: { ...emptyView, section: 'yearly' },
      dropped: ['year "1800"'],
    })
    expect(parse('?section=static&year=2005').dropped).toEqual(['year "2005"'])
  })
})

describe('full view in the address bar', () => {
  it('is read when a section is open', () => {
    expect(parse('?section=yearly&view=charts').view.full).toBe(true)
    expect(parse('?section=yearly').view.full).toBe(false)
  })
  it('is dropped without a section, or with an unknown value', () => {
    expect(parse('?view=charts')).toEqual({ view: emptyView, dropped: ['view "charts" without a section'] })
    expect(parse('?section=yearly&view=map3d')).toEqual({
      view: { ...emptyView, section: 'yearly' },
      dropped: ['view "map3d"'],
    })
  })
})
