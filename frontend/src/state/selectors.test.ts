import { describe, expect, it } from 'vitest'
import type { Catalogue, Layer, Place, Section } from '../api/types'
import {
  ancestors,
  clickTarget,
  effectiveYear,
  observationIndex,
  searchPlaces,
  sectionsWithActiveLayers,
  tidyYear,
  timeObservations,
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
const sparse: Catalogue = {
  basemap_style_url: '',
  sections: [section('sparse', { first: 2017, last: 2023, available: [2017, 2019, 2023] })],
  layers: [layer('annual', 'sparse', { first: 2017, last: 2023, available: [2017, 2019, 2023] })],
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

describe('timeObservations', () => {
  it('is empty when nothing on screen has years', () => {
    expect(timeObservations(view({}), catalogue)).toEqual([])
    expect(timeObservations(view({ section: 'static', layers: [active('ls')] }), catalogue)).toEqual([])
  })

  it('lists every year of a continuous range', () => {
    expect(timeObservations(view({ section: 'yearly' }), catalogue)).toEqual(
      Array.from({ length: 11 }, (_, i) => 2000 + i),
    )
  })

  it('lists only the observations a sparse range declares', () => {
    expect(timeObservations(view({ section: 'sparse' }), sparse)).toEqual([2017, 2019, 2023])
  })

  it('comes from an active layer even when its section is closed', () => {
    expect(timeObservations(view({ layers: [active('ly')] }), catalogue)).toEqual(
      Array.from({ length: 11 }, (_, i) => 1995 + i),
    )
  })

  it('counts hidden layers', () => {
    const hidden = { id: 'ly', opacity: 1, hidden: true }
    expect(timeObservations(view({ layers: [hidden] }), catalogue)).toHaveLength(11)
  })

  it('combines the section and every active layer, once each', () => {
    const v = view({ section: 'yearly', layers: [active('ly'), active('lz')] })
    expect(timeObservations(v, catalogue)).toEqual(Array.from({ length: 26 }, (_, i) => 1995 + i))
  })

  it('ignores ids that are not in the catalogue', () => {
    expect(timeObservations(view({ section: 'ghost', layers: [active('ghost')] }), catalogue)).toEqual([])
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
  it('shows the nearest observation a sparse range declares', () => {
    const sparseYears = { first: 2017, last: 2023, available: [2017, 2019, 2023] }
    expect(effectiveYear(sparseYears, 2019)).toBe(2019)
    expect(effectiveYear(sparseYears, 2018)).toBe(2017)
    expect(effectiveYear(sparseYears, 2021)).toBe(2019)
    expect(effectiveYear(sparseYears, 2030)).toBe(2023)
  })
  it('prefers the earlier observation when two are equally near', () => {
    const sparseYears = { first: 2017, last: 2023, available: [2017, 2019, 2023] }
    expect(effectiveYear(sparseYears, 2016)).toBe(2017)
    expect(effectiveYear(sparseYears, 2020)).toBe(2019)
  })
})

describe('observationIndex', () => {
  it('places a year in the observation list', () => {
    expect(observationIndex([2017, 2019, 2023], 2019)).toBe(1)
  })

  it('is the last observation when no year is chosen', () => {
    expect(observationIndex([2017, 2019, 2023], null)).toBe(2)
  })

  it('places a year that is not an observation at its nearest', () => {
    expect(observationIndex([2017, 2019, 2023], 2021)).toBe(1)
  })

  it('is nothing without observations', () => {
    expect(observationIndex([], 2019)).toBe(-1)
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

describe('tidyYear', () => {
  it('clears the year when nothing on screen has years', () => {
    expect(tidyYear(view({ section: 'static', year: 2005 }), catalogue)).toBeNull()
    expect(tidyYear(view({ year: 2005 }), catalogue)).toBeNull()
  })
  it('keeps a year inside the range', () => {
    expect(tidyYear(view({ section: 'yearly', year: 2005 }), catalogue)).toBe(2005)
  })
  it('clamps a year outside the range', () => {
    expect(tidyYear(view({ section: 'yearly', year: 1990 }), catalogue)).toBe(2000)
    expect(tidyYear(view({ section: 'yearly', year: 2030 }), catalogue)).toBe(2010)
  })
  it('leaves the latest-year default alone', () => {
    expect(tidyYear(view({ section: 'yearly' }), catalogue)).toBeNull()
  })
  it('snaps a year that is not an observation to the nearest one', () => {
    expect(tidyYear(view({ section: 'sparse', year: 2021 }), sparse)).toBe(2019)
  })
  it('keeps an observation as it is', () => {
    expect(tidyYear(view({ section: 'sparse', year: 2023 }), sparse)).toBe(2023)
  })
})
