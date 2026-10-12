import { describe, expect, it } from 'vitest'
import { fieldArt, fieldRings, layerColours, shade } from './fieldArt'

describe('shade', () => {
  it('moves a colour toward white or black', () => {
    expect(shade('#204060', 0)).toBe('#204060')
    expect(shade('#204060', 1)).toBe('#ffffff')
    expect(shade('#204060', -1)).toBe('#000000')
    expect(shade('#000000', 0.5)).toBe('#808080')
  })
})

describe('layerColours', () => {
  it('takes a ramp’s colours as they are', () => {
    const colours = ['#111111', '#222222', '#333333', '#444444']
    expect(layerColours({ legend: { type: 'ramp', colours, min: 0, max: 1, unit: '' } })).toEqual(colours)
  })

  it('takes the colours of a legend of classes in order', () => {
    const items = ['#aa0000', '#00aa00', '#0000aa'].map((colour, i) => ({ colour, label: String(i) }))
    expect(layerColours({ legend: { type: 'classes', items } })).toEqual(['#aa0000', '#00aa00', '#0000aa'])
  })

  it('gives a layer of one colour a lighter and a darker shade of it', () => {
    const [light, own, dark] = layerColours({ legend: { type: 'classes', items: [{ colour: '#2e7d32', label: 'Forest' }] } })
    expect(own).toBe('#2e7d32')
    expect(light).not.toBe(own)
    expect(dark).not.toBe(own)
  })

  it('pads two colours to three and has greys for a layer with no legend', () => {
    const two = ['#ffffff', '#000000']
    expect(layerColours({ legend: { type: 'ramp', colours: two, min: 0, max: 1, unit: '' } })).toHaveLength(3)
    expect(layerColours({ legend: null })).toHaveLength(3)
  })
})

describe('fieldArt', () => {
  const colours = ['#313695', '#abd9e9', '#ffffbf', '#fdae61', '#a50026']

  it('is the same picture for the same layer every time, and another for another layer', () => {
    expect(fieldArt(colours, 'temperature')).toBe(fieldArt(colours, 'temperature'))
    expect(fieldArt(colours, 'temperature')).not.toBe(fieldArt(colours, 'dew-point'))
  })

  it('can leave its rings out, to be drawn apart as the very rings it would have had', () => {
    const whole = fieldArt(colours, 'temperature')
    const bare = fieldArt(colours, 'temperature', { rings: false })
    expect(bare.startsWith('radial-gradient(')).toBe(true)
    expect(`${fieldRings('temperature')}, ${bare}`).toBe(whole)
  })

  it('is built from the layer’s own colours, both ends included', () => {
    const art = fieldArt(colours, 'temperature')
    expect(art).toContain('#313695')
    expect(art).toContain('#a50026')
    expect(art.startsWith('repeating-radial-gradient(')).toBe(true)
  })
})
