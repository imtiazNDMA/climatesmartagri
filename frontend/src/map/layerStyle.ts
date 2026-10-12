import type { Layer } from '../api/types'

/** The fill for a shape with no value, or a value the legend does not list. */
export const NO_VALUE_COLOUR = '#d9d8d2'

type Ramp = Extract<NonNullable<Layer['legend']>, { type: 'ramp' }>

/**
 * The value the ramp's colour at `index` stands for. Colours are spread evenly from the minimum
 * to the maximum, unless the ramp names the value of its middle colour: then each half is spread
 * on its own, so a balance keeps its neutral colour at zero however lopsided the two sides are.
 */
export function rampValue(legend: Ramp, index: number): number {
  const { colours, min, max, mid } = legend
  const last = colours.length - 1
  if (mid === null || mid === undefined || mid <= min || mid >= max || last % 2 !== 0) {
    return min + ((max - min) * index) / last
  }
  const half = last / 2
  return index <= half ? min + ((mid - min) * index) / half : mid + ((max - mid) * (index - half)) / half
}

const channels = (hex: string) => [1, 3, 5].map((at) => parseInt(hex.slice(at, at + 2), 16))

/** The colour part of the way from one six-digit hex colour to another. */
function mix(from: string, to: string, share: number): string {
  const [a, b] = [channels(from), channels(to)]
  return `#${a.map((start, i) => Math.round(start + (b[i] - start) * share).toString(16).padStart(2, '0')).join('')}`
}

/**
 * The colour one shape of a layer is drawn in, worked out the way the map does it,
 * so a popup can wear the colour of the shape that was clicked.
 */
export function shapeColour(layer: Layer, properties: Record<string, unknown> | null | undefined): string {
  const { legend, property } = layer
  if (!legend) return NO_VALUE_COLOUR
  const raw = property ? properties?.[property] : undefined
  if (legend.type === 'classes') {
    const valued = legend.items.filter((item) => item.value !== null && item.value !== undefined)
    if (!property || valued.length === 0) return legend.items[0].colour
    return valued.find((item) => item.value === String(raw ?? ''))?.colour ?? NO_VALUE_COLOUR
  }
  const { colours, min, max } = legend
  const last = colours.length - 1
  if (!property) return colours[last]
  const value = typeof raw === 'number' ? raw : raw === null || raw === undefined || raw === '' ? NaN : Number(raw)
  if (Number.isNaN(value)) return NO_VALUE_COLOUR
  if (max <= min) return colours[last]
  if (value <= rampValue(legend, 0)) return colours[0]
  for (let i = 1; i <= last; i++) {
    const [low, high] = [rampValue(legend, i - 1), rampValue(legend, i)]
    if (value <= high) return mix(colours[i - 1], colours[i], (value - low) / (high - low))
  }
  return colours[last]
}

/**
 * The colours for the shapes a layer marks as extreme: those marked "low" wear the legend's first
 * colour and those marked "high" its last. Null when the layer has no colour ramp to take them from.
 */
export function extremeColours(layer: Layer): { low: string; high: string } | null {
  if (layer.legend?.type !== 'ramp') return null
  const { colours } = layer.legend
  return { low: colours[0], high: colours[colours.length - 1] }
}

/** How strongly the blink shows at a moment in time: it swells and fades about once every 1.4 seconds. */
export function glowStrength(milliseconds: number): number {
  return 0.1 + 0.9 * (0.5 - 0.5 * Math.cos((milliseconds / 1400) * 2 * Math.PI))
}

/** The MapLibre fill colour for a shape layer, derived from its legend. */
export function fillColour(layer: Layer): unknown {
  const { legend, property } = layer
  if (!legend) return NO_VALUE_COLOUR

  if (legend.type === 'classes') {
    const valued = legend.items.filter((item) => item.value !== null && item.value !== undefined)
    if (!property || valued.length === 0) return legend.items[0].colour
    return [
      'match',
      ['to-string', ['get', property]],
      ...valued.flatMap((item) => [item.value as string, item.colour]),
      NO_VALUE_COLOUR,
    ]
  }

  const { colours, min, max } = legend
  if (!property) return colours[colours.length - 1]
  if (max <= min) return ['case', ['has', property], colours[colours.length - 1], NO_VALUE_COLOUR]
  const stops = colours.flatMap((colour, i) => [rampValue(legend, i), colour])
  return [
    'case',
    ['has', property],
    ['interpolate', ['linear'], ['to-number', ['get', property]], ...stops],
    NO_VALUE_COLOUR,
  ]
}
