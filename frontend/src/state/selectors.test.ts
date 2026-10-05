import { describe, expect, it } from 'vitest'
import type { Catalogue, Layer, Place, Section } from '../api/types'
import {
  ancestors,
  clickTarget,
  effectiveYear,
  searchPlaces,
  sectionsWithActiveLayers,
  timeRange,
} from './selectors'
import { emptyView, type View } from './viewState'

const section = (id: string, years: Section['years'] = null): Section => ({
  id, title: id, icon: 'trees', order: 1, status: 'ready', summary: '', place_levels: ['national'], years,
})
const layer = (id: string, sectionId: string, years: Layer['years'] = null): Layer => ({
  id, section_id: sectionId, title: id, kind: 'raster', status: 'ready',
  legend: { type: 'classes', items: [{ colour: '#000', label: id }] }, years, default_opacity: 1,
})
const catalogue: Catalogue = {
  basemap_style_url: '',
  sections: [section('yearly', { first: 2000, last: 2010 }), section('static')],
  layers: [
    layer('ly', 'yearly', { first: 1995, last: 2005 }),
    layer('ls', 'static'),
    layer('lz', 'static', { first: 2008, last: 2020 }),
  ],
}
const place = (id: string, name: string, level: Place['level'], parent: string | null): Place => ({
  id, name, level, parent_id: parent, bbox: [0, 0, 1, 1],
})
const places: Place[] = [
  place('PK', 'Pakistan', 'national', null),
  place('PK1', 'Alpha', 'province', 'PK'),
  place('PK2', 'Beta', 'province', 'PK'),
  place('PK101', 'District One', 'district', 'PK1'),
  place('PK102', 'District Two', 'district', 'PK1'),
  place('PK201', 'District Three', 'district', 'PK2'),
]
const view = (patch: Partial<View>): View => ({ ...emptyView, ...patch })
const active = (id: string) => ({ id, opacity: 1, hidden: false })

describe('timeRange', () => {
  it('is null when nothing on screen has years', () => {
    expect(timeRange(view({}), catalogue)).toBeNull()
    expect(timeRange(view({ section: 'static', layers: [active('ls')] }), catalogue)).toBeNull()
  })

  it('comes from the open section', () => {
    expect(timeRange(view({ section: 'yearly' }), catalogue)).toEqual({ first: 2000, last: 2010 })
  })

  it('comes from an active layer even when its section is closed', () => {
    expect(timeRange(view({ layers: [active('ly')] }), catalogue)).toEqual({ first: 1995, last: 2005 })
  })

  it('counts hidden layers', () => {
    const hidden = { id: 'ly', opacity: 1, hidden: true }
    expect(timeRange(view({ layers: [hidden] }), catalogue)).toEqual({ first: 1995, last: 2005 })
  })

  it('is the widest span across the section and all active layers', () => {
    const v = view({ section: 'yearly', layers: [active('ly'), active('lz')] })
    expect(timeRange(v, catalogue)).toEqual({ first: 1995, last: 2020 })
  })

  it('ignores ids that are not in the catalogue', () => {
    expect(timeRange(view({ section: 'ghost', layers: [active('ghost')] }), catalogue)).toBeNull()
  })
})

describe('effectiveYear', () => {
  const years = { first: 2000, last: 2010 }
  it('is null without a range', () => {
    expect(effectiveYear(null, 2005)).toBeNull()
  })
  it('defaults to the last year', () => {
    expect(effectiveYear(years, null)).toBe(2010)
  })
  it('keeps a year inside the range and clamps one outside', () => {
    expect(effectiveYear(years, 2005)).toBe(2005)
    expect(effectiveYear(years, 1990)).toBe(2000)
    expect(effectiveYear(years, 2030)).toBe(2010)
  })
})

describe('sectionsWithActiveLayers', () => {
  it('lists the sections that own an active layer', () => {
    const result = sectionsWithActiveLayers(view({ layers: [active('ls'), active('ghost')] }), catalogue)
    expect([...result]).toEqual(['static'])
  })
})

describe('ancestors', () => {
  it('is just the country when nothing is selected', () => {
    expect(ancestors(places, null).map((p) => p.id)).toEqual(['PK'])
  })
  it('runs from the country down to the selection', () => {
    expect(ancestors(places, 'PK1').map((p) => p.id)).toEqual(['PK', 'PK1'])
    expect(ancestors(places, 'PK101').map((p) => p.id)).toEqual(['PK', 'PK1', 'PK101'])
  })
  it('falls back to the country for an unknown place', () => {
    expect(ancestors(places, 'XX').map((p) => p.id)).toEqual(['PK'])
  })
  it('is empty when no places are loaded', () => {
    expect(ancestors([], 'PK1')).toEqual([])
  })
})

describe('clickTarget', () => {
  it('selects the province first', () => {
    expect(clickTarget(places, null, 'PK101')).toBe('PK1')
  })
  it('drills into the district inside the selected province', () => {
    expect(clickTarget(places, 'PK1', 'PK101')).toBe('PK101')
  })
  it('moves between districts of the same province', () => {
    expect(clickTarget(places, 'PK101', 'PK102')).toBe('PK102')
  })
  it('switches to a different province', () => {
    expect(clickTarget(places, 'PK1', 'PK201')).toBe('PK2')
    expect(clickTarget(places, 'PK101', 'PK201')).toBe('PK2')
  })
  it('is null for a district it does not know', () => {
    expect(clickTarget(places, null, 'XX')).toBeNull()
  })
  it('selects the district directly when its province is not loaded', () => {
    const orphan = [place('PK', 'Pakistan', 'national', null), place('D1', 'Lone', 'district', 'P9')]
    expect(clickTarget(orphan, null, 'D1')).toBe('D1')
  })
})

describe('searchPlaces', () => {
  it('matches part of a name regardless of case and surrounding spaces', () => {
    expect(searchPlaces(places, '  dIsTrIcT t ').map((p) => p.id)).toEqual(['PK201', 'PK102'])
  })
  it('never returns the country', () => {
    expect(searchPlaces(places, 'pak')).toEqual([])
  })
  it('returns nothing for an empty or blank query', () => {
    expect(searchPlaces(places, '')).toEqual([])
    expect(searchPlaces(places, '   ')).toEqual([])
  })
  it('puts names that start with the query first and respects the limit', () => {
    expect(searchPlaces(places, 'a').map((p) => p.id)[0]).toBe('PK1')
    expect(searchPlaces(places, 'district', 2)).toHaveLength(2)
  })
})
