import { describe, expect, it } from 'vitest'
import type { ForecastCatalogue, ForecastLayer } from '../api/types'
import { axisValues, buildEntries, entryOf, firstLayer, layerForAxis } from './entries'

const layer = (id: string, group: string, offered = true): ForecastLayer => ({
  id, title: `Title of ${id}`, group, unit: 'mm', colours: ['#fff', '#00f'], min: 0, max: 1, ranges: {},
  levels: offered ? { 'model-a': [0] } : {},
})

const forecast: ForecastCatalogue = {
  configured: true,
  bbox: [55, 18, 85, 42],
  models: [{ id: 'model-a', label: 'Model A' }],
  groups: [
    { id: 'precipitation', title: 'Precipitation' },
    { id: 'thermodynamics', title: 'Temperature' },
  ],
  layers: [
    layer('rain-3h', 'precipitation'), layer('rain-24h', 'precipitation'), layer('rain-7d', 'precipitation'),
    layer('rainfall-24h', 'precipitation'), layer('snowfall-6h', 'precipitation'), layer('snowfall-24h', 'precipitation'),
    layer('sleet-24h', 'precipitation', false),
    layer('precipitation-type', 'precipitation'),
    layer('temperature', 'thermodynamics'), layer('temperature-max', 'thermodynamics', false),
    layer('temperature-min', 'thermodynamics', false),
    layer('cape', 'thermodynamics'), layer('cin', 'thermodynamics', false),
  ],
}
const { entries, unavailable } = buildEntries(forecast)
const precipitation = entries[0]

describe('buildEntries', () => {
  it('gathers the layers of one quantity into an entry, in catalogue order', () => {
    expect(entries.map((entry) => entry.id)).toEqual(['precipitation', 'precipitation-type', 'temperature', 'cape'])
    expect(precipitation.title).toBe('Precipitation')
    expect(precipitation.axes).toEqual(['Kind', 'Period'])
    expect(precipitation.options.map((option) => option.layer.id)).toEqual([
      'rain-3h', 'rain-24h', 'rain-7d', 'rainfall-24h', 'snowfall-6h', 'snowfall-24h',
    ])
  })

  it('leaves a family with one layer on offer as that layer, under its own title and with no choosers', () => {
    const temperature = entries[2]
    expect(temperature).toMatchObject({ id: 'temperature', title: 'Title of temperature', axes: [] })
    expect(temperature.options).toHaveLength(1)
  })

  it('lists the layers with no current data by group, and keeps them out of the entries', () => {
    expect(unavailable).toEqual({
      precipitation: ['Title of sleet-24h'],
      thermodynamics: ['Title of temperature-max', 'Title of temperature-min', 'Title of cin'],
    })
  })
})

describe('finding and starting an entry', () => {
  it('finds the entry a layer belongs to', () => {
    expect(entryOf(entries, 'snowfall-6h')?.id).toBe('precipitation')
    expect(entryOf(entries, 'cape')?.id).toBe('cape')
    expect(entryOf(entries, 'nope')).toBeUndefined()
    expect(entryOf(entries, undefined)).toBeUndefined()
  })

  it('starts on the preferred layer when there is one, else the first', () => {
    expect(firstLayer(precipitation).id).toBe('rain-24h')
    expect(firstLayer(entries[3]).id).toBe('cape')
  })
})

describe('the choosers', () => {
  it('offer each value once, marking the one on the map and those that fit the other axis', () => {
    // Snow over 24 hours is on the map.
    expect(axisValues(precipitation, 0, ['Snow', '24h'])).toEqual([
      { value: 'All', on: false, fits: true },
      { value: 'Rain', on: false, fits: true },
      { value: 'Snow', on: true, fits: true },
    ])
    expect(axisValues(precipitation, 1, ['Snow', '24h'])).toEqual([
      { value: '3h', on: false, fits: false },
      { value: '24h', on: true, fits: true },
      { value: '7 days', on: false, fits: false },
      { value: '6h', on: false, fits: true },
    ])
  })

  it('move to the layer with the new value and the other axis kept, or the first with that value', () => {
    expect(layerForAxis(precipitation, ['Snow', '24h'], 1, '6h')?.id).toBe('snowfall-6h')
    expect(layerForAxis(precipitation, ['Snow', '24h'], 0, 'Rain')?.id).toBe('rainfall-24h')
    // There is no snow over 7 days: the period wins and the kind falls back.
    expect(layerForAxis(precipitation, ['Snow', '24h'], 1, '7 days')?.id).toBe('rain-7d')
    expect(layerForAxis(precipitation, ['Snow', '24h'], 0, 'Hail')).toBeUndefined()
  })
})
