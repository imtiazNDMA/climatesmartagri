import { describe, expect, it } from 'vitest'
import type { Layer } from '../api/types'
import { figureBar, groupLayers, layerScope, layerSwatch } from './panelParts'

const layer = (id: string, title: string, legend: Layer['legend'] = null): Layer => ({
  id, section_id: 's', title, kind: 'geojson', status: 'ready', property: 'value', default_opacity: 1, legend,
} as Layer)

describe('layerScope', () => {
  it('takes the scope off the end of a title', () => {
    expect(layerScope('Surface water irrigation (district)')).toEqual({ name: 'Surface water irrigation', scope: 'district' })
    expect(layerScope('Recommended irrigation practice (tehsil)')).toEqual({ name: 'Recommended irrigation practice', scope: 'tehsil' })
  })

  it('leaves a title without one alone, and brackets that are not a scope', () => {
    expect(layerScope('Forest cover')).toEqual({ name: 'Forest cover', scope: null })
    expect(layerScope('Emissions (2021)')).toEqual({ name: 'Emissions (2021)', scope: null })
  })
})

describe('groupLayers', () => {
  it('gathers layers by scope, keeping the order they came in', () => {
    const groups = groupLayers([
      layer('a', 'Practice (tehsil)'), layer('b', 'Surface (district)'), layer('c', 'Forest'), layer('d', 'Balance (district)'),
    ])
    expect(groups.map((g) => [g.scope, g.layers.map((l) => l.id)])).toEqual([
      ['tehsil', ['a']], ['district', ['b', 'd']], [null, ['c']],
    ])
  })
})

describe('layerSwatch', () => {
  it('runs a ramp from end to end and shows classes as equal blocks', () => {
    const ramp = layer('r', 'R', { type: 'ramp', colours: ['#ffffff', '#ff0000'], min: 0, max: 1, unit: '' })
    expect(layerSwatch(ramp)).toBe('linear-gradient(to right, #ffffff, #ff0000)')
    const classes = layer('c', 'C', { type: 'classes', items: [{ colour: '#111111', label: 'A' }, { colour: '#222222', label: 'B' }] })
    expect(layerSwatch(classes)).toBe('linear-gradient(to right, #111111 0% 50%, #222222 50% 100%)')
    const one = layer('o', 'O', { type: 'classes', items: [{ colour: '#333333', label: 'A' }] })
    expect(layerSwatch(one)).toBe('#333333')
  })

  it('is plain grey for a layer with no legend', () => {
    expect(layerSwatch(layer('n', 'N'))).toBe('#cbd5e1')
  })
})

describe('figureBar', () => {
  it('fills by the share the data gives, or by the value of a percentage', () => {
    expect(figureBar({ label: 'Groundwater', value: 12.78, unit: 'million acres', share: 30.9 })).toBe(30.9)
    expect(figureBar({ label: 'Share irrigated', value: 80, unit: '%' })).toBe(80)
  })

  it('has no bar for a plain amount or a missing value, and never runs past its ends', () => {
    expect(figureBar({ label: 'Land', value: 41.33, unit: 'million acres' })).toBeNull()
    expect(figureBar({ label: 'Share', value: null, unit: '%' })).toBeNull()
    expect(figureBar({ label: 'Share', value: 140, unit: '%' })).toBe(100)
    expect(figureBar({ label: 'Share', value: -5, unit: '%' })).toBe(0)
  })
})
