import type { Layer } from '../api/types'

/** A number from a string, the same every time, so each layer keeps its own picture. */
function seedOf(text: string): number {
  let seed = 2166136261
  for (let i = 0; i < text.length; i++) seed = Math.imul(seed ^ text.charCodeAt(i), 16777619)
  return seed >>> 0
}

const channels = (hex: string) => [1, 3, 5].map((at) => parseInt(hex.slice(at, at + 2), 16))

/** A six-digit hex colour moved part of the way to white (a positive share) or to black (a negative one). */
export function shade(hex: string, share: number): string {
  const target = share >= 0 ? 255 : 0
  const amount = Math.abs(share)
  return `#${channels(hex).map((c) => Math.round(c + (target - c) * amount).toString(16).padStart(2, '0')).join('')}`
}

/**
 * The colours a map layer is drawn in, in legend order, as the picture on its card needs them: at least
 * three, so a layer of one colour is given a lighter and a darker shade of it.
 */
export function layerColours(layer: Pick<Layer, 'legend'>): string[] {
  const { legend } = layer
  if (!legend) return ['#e2e8f0', '#cbd5e1', '#94a3b8']
  const colours = legend.type === 'ramp' ? legend.colours : legend.items.map((item) => item.colour)
  if (colours.length >= 3) return colours
  if (colours.length === 2) return [colours[0], shade(colours[0], 0.35), colours[1]]
  return [shade(colours[0], 0.55), colours[0], shade(colours[0], -0.3)]
}

/** Numbers from 0 to 1 that follow from a key, the same run of them every time. */
function sequence(key: string): () => number {
  let state = seedOf(key)
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0
    return state / 4294967296
  }
}

const ringsAt = (next: () => number) =>
  `repeating-radial-gradient(circle at ${Math.round(20 + next() * 60)}% ${Math.round(20 + next() * 60)}%, transparent 0 13px, rgb(255 255 255 / 20%) 13px 14px)`

/** The contour rings of a layer's picture alone, for where they are drawn as a layer of their own. */
export function fieldRings(key: string): string {
  return ringsAt(sequence(key))
}

/**
 * A layer's colours drawn as a small chart: soft patches of them over a wash from one end of the scale to
 * the other, with faint contour rings round a point. It is a picture of the layer's colours, not of its
 * data. A CSS background-image built from gradients alone, and the same for the same key every time.
 */
export function fieldArt(colours: string[], key: string, { rings = true }: { rings?: boolean } = {}): string {
  const next = sequence(key)
  const last = colours.length - 1
  const at = (share: number) => colours[Math.round(share * last)]
  const patch = (colour: string, size: number) => {
    const x = Math.round(8 + next() * 84)
    const y = Math.round(10 + next() * 80)
    return `radial-gradient(ellipse ${size}% ${Math.round(size * 0.8)}% at ${x}% ${y}%, ${colour} 0%, transparent 72%)`
  }
  const ringsLayer = ringsAt(next)
  return [
    ...(rings ? [ringsLayer] : []),
    patch(at(1), 46),
    patch(at(0), 52),
    patch(at(0.75), 40),
    patch(at(0.25), 44),
    `linear-gradient(${Math.round(next() * 360)}deg, ${at(0.15)}, ${at(0.5)}, ${at(0.85)})`,
  ].join(', ')
}
