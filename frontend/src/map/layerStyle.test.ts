import { describe, expect, it } from 'vitest'
import type { Layer } from '../api/types'
import { fillColour, NO_VALUE_COLOUR } from './layerStyle'

const base: Layer = {
  id: 'shapes', section_id: 's', title: 'Shapes', kind: 'geojson', status: 'ready',
  property: 'practice', years: null, default_opacity: 1,
  legend: {
    type: 'classes',
    items: [
      { colour: '#111111', label: 'Drip', value: 'Drip' },
      { colour: '#222222', label: 'Sprinkler', value: 'SP' },
    ],
  },
}

describe('fillColour', () => {
  it('matches each legend value to its colour, with a neutral colour for anything else', () => {
    expect(fillColour(base)).toEqual([
      'match', ['to-string', ['get', 'practice']], 'Drip', '#111111', 'SP', '#222222', NO_VALUE_COLOUR,
    ])
  })

  it('interpolates a ramp between its minimum and maximum, and greys out features with no value', () => {
    const ramp: Layer = {
      ...base, property: 'value',
      legend: { type: 'ramp', colours: ['#aaaaaa', '#555555', '#000000'], min: 0, max: 100, unit: '%' },
    }
    expect(fillColour(ramp)).toEqual([
      'case',
      ['has', 'value'],
      ['interpolate', ['linear'], ['to-number', ['get', 'value']], 0, '#aaaaaa', 50, '#555555', 100, '#000000'],
      NO_VALUE_COLOUR,
    ])
  })

  it('falls back to a single colour when the legend has no values to match', () => {
    const plain: Layer = {
      ...base, legend: { type: 'classes', items: [{ colour: '#333333', label: 'All' }] },
    }
    expect(fillColour(plain)).toBe('#333333')
  })

  it('uses the neutral colour when there is no legend or property', () => {
    expect(fillColour({ ...base, legend: null })).toBe(NO_VALUE_COLOUR)
    expect(fillColour({ ...base, property: null })).toBe('#111111')
  })

  it('copes with a ramp whose minimum equals its maximum', () => {
    const flat: Layer = {
      ...base, property: 'value',
      legend: { type: 'ramp', colours: ['#aaaaaa', '#000000'], min: 5, max: 5, unit: '' },
    }
    expect(fillColour(flat)).toEqual(['case', ['has', 'value'], '#000000', NO_VALUE_COLOUR])
  })
})
