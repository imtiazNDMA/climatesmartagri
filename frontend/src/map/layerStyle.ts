import type { Layer } from '../api/types'

/** The fill for a shape with no value, or a value the legend does not list. */
export const NO_VALUE_COLOUR = '#d9d8d2'

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
  const stops = colours.flatMap((colour, i) => [min + ((max - min) * i) / (colours.length - 1), colour])
  return [
    'case',
    ['has', property],
    ['interpolate', ['linear'], ['to-number', ['get', property]], ...stops],
    NO_VALUE_COLOUR,
  ]
}
