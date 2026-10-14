import type { Figure, Layer } from '../api/types'

const SCOPE = /\s*\((tehsil|district|province)\)$/i

/** A layer's title without the "(district)" on its end, and that word, which groups the layer in the panel. */
export function layerScope(title: string): { name: string; scope: string | null } {
  const match = SCOPE.exec(title)
  return match ? { name: title.slice(0, match.index), scope: match[1].toLowerCase() } : { name: title, scope: null }
}

/** A section's layers in the order given, gathered under the first appearance of each scope. */
export function groupLayers(layers: Layer[]): { scope: string | null; layers: Layer[] }[] {
  const groups: { scope: string | null; layers: Layer[] }[] = []
  for (const layer of layers) {
    const { scope } = layerScope(layer.title)
    const group = groups.find((g) => g.scope === scope)
    if (group) group.layers.push(layer)
    else groups.push({ scope, layers: [layer] })
  }
  return groups
}

/** A small strip of a layer's legend colours, as a CSS background, so a layer can be told by its colours. */
export function layerSwatch(layer: Layer): string {
  const { legend } = layer
  if (!legend) return '#cbd5e1'
  if (legend.type === 'ramp') return `linear-gradient(to right, ${legend.colours.join(', ')})`
  const colours = legend.items.slice(0, 4).map((item) => item.colour)
  if (colours.length === 1) return colours[0]
  const step = 100 / colours.length
  return `linear-gradient(to right, ${colours.map((c, i) => `${c} ${i * step}% ${(i + 1) * step}%`).join(', ')})`
}

/** What a layer's colours stand for, in a few words for its card: its classes, or the two ends of its scale. */
export function layerAbout(layer: Pick<Layer, 'legend'>): string {
  const { legend } = layer
  if (!legend) return ''
  if (legend.type === 'classes') {
    // A class can appear under several colours; it is named once.
    const labels = [...new Set(legend.items.map((item) => item.label))]
    // Long categorical legends belong in the map legend, not in a compact switch card.
    if (labels.length > 3 || labels.some((label) => label.includes(','))) {
      return `${labels.length} mapped ${labels.length === 1 ? 'category' : 'categories'}`
    }
    return labels.join(', ')
  }
  // The far end is written mid-sentence, so it starts small: "Less land to more land".
  const far = legend.max_label || 'high'
  const ends = `${legend.min_label || 'Low'} to ${far.charAt(0).toLowerCase()}${far.slice(1)}`
  return legend.unit ? `${ends}, ${legend.unit}` : ends
}

/**
 * How full the bar under a figure is, from 0 to 100, or null for a figure that has no bar.
 * A figure that is itself a percentage fills by its value; others by the share the data gives them.
 */
export function figureBar(figure: Figure): number | null {
  const share = typeof figure.share === 'number' ? figure.share : null
  const own = figure.unit === '%' && typeof figure.value === 'number' ? figure.value : null
  const filled = share ?? own
  return filled === null || Number.isNaN(filled) ? null : Math.min(100, Math.max(0, filled))
}
