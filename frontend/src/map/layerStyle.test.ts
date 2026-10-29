import { describe, expect, it } from 'vitest'
import type { Layer } from '../api/types'
import { extremeColours, fillColour, glowStrength, NO_VALUE_COLOUR, shapeColour } from './layerStyle'

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

  it('keeps the middle colour of a two-way ramp at its named value, however lopsided the sides', () => {
    const balance: Layer = {
      ...base, property: 'value',
      legend: {
        type: 'ramp', colours: ['#0000ff', '#8888ff', '#dddddd', '#ff8888', '#ff0000'],
        min: -200, max: 700, mid: 0, unit: 'ha',
      },
    }
    expect(fillColour(balance)).toEqual([
      'case',
      ['has', 'value'],
      ['interpolate', ['linear'], ['to-number', ['get', 'value']],
        -200, '#0000ff', -100, '#8888ff', 0, '#dddddd', 350, '#ff8888', 700, '#ff0000'],
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

describe('shapeColour', () => {
  const classes: Layer = {
    ...base, property: 'kind',
    legend: { type: 'classes', items: [{ colour: '#111111', label: 'A', value: 'a' }, { colour: '#222222', label: 'B', value: 'b' }] },
  }
  const ramp: Layer = {
    ...base, property: 'value',
    legend: { type: 'ramp', colours: ['#000000', '#808080', '#ffffff'], min: -100, max: 400, mid: 0, unit: 'ha' },
  }

  it('is the legend colour of the class the shape belongs to, and grey for one the legend does not list', () => {
    expect(shapeColour(classes, { kind: 'b' })).toBe('#222222')
    expect(shapeColour(classes, { kind: 'z' })).toBe(NO_VALUE_COLOUR)
    expect(shapeColour(classes, {})).toBe(NO_VALUE_COLOUR)
  })

  it('is the colour the ramp gives a value, each side of the middle on its own scale', () => {
    expect(shapeColour(ramp, { value: 0 })).toBe('#808080')
    expect(shapeColour(ramp, { value: -50 })).toBe('#404040')
    expect(shapeColour(ramp, { value: 200 })).toBe('#c0c0c0')
  })

  it('stops at the ends of the ramp, and is grey for a shape with no value', () => {
    expect(shapeColour(ramp, { value: -900 })).toBe('#000000')
    expect(shapeColour(ramp, { value: 900 })).toBe('#ffffff')
    expect(shapeColour(ramp, {})).toBe(NO_VALUE_COLOUR)
  })
})

describe('picking out extreme shapes', () => {
  it('uses the two ends of the colour ramp, and nothing for a layer of classes', () => {
    const ramp: Layer = {
      ...base, property: 'value',
      legend: { type: 'ramp', colours: ['#0000ff', '#dddddd', '#ff0000'], min: -1, max: 1, mid: 0, unit: '' },
    }
    expect(extremeColours(ramp)).toEqual({ low: '#0000ff', high: '#ff0000' })
    expect(extremeColours(base)).toBeNull()
  })

  it('swells and fades without ever going out', () => {
    const strengths = Array.from({ length: 29 }, (_, i) => glowStrength(i * 50))
    expect(Math.min(...strengths)).toBeCloseTo(0.1)
    expect(Math.max(...strengths)).toBeCloseTo(1)
    expect(glowStrength(1400)).toBeCloseTo(glowStrength(0))
  })
})
