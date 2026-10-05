import { COUNTRY_ID, type Catalogue, type Place } from '../api/types'
import { timeRange } from './selectors'
import type { ActiveLayer, View } from './viewState'

/** Ids are URL-safe by catalogue rule, so the query is built by hand to stay readable. */
export function serializeView(view: View): string {
  const parts: string[] = []
  if (view.section) parts.push(`section=${view.section}`)
  if (view.layers.length) parts.push(`layers=${view.layers.map((l) => `${l.id}:${l.opacity}`).join(',')}`)
  const hidden = view.layers.filter((l) => l.hidden).map((l) => l.id)
  if (hidden.length) parts.push(`hidden=${hidden.join(',')}`)
  if (view.place) parts.push(`place=${encodeURIComponent(view.place)}`)
  if (view.year !== null) parts.push(`year=${view.year}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

export function parseView(search: string, catalogue: Catalogue, places: Place[]): { view: View; dropped: string[] } {
  const params = new URLSearchParams(search)
  const dropped: string[] = []

  let section: string | null = null
  const rawSection = params.get('section')
  if (rawSection) {
    if (catalogue.sections.some((s) => s.id === rawSection)) section = rawSection
    else dropped.push(`section "${rawSection}"`)
  }

  const layers: ActiveLayer[] = []
  for (const token of (params.get('layers') ?? '').split(',')) {
    if (!token) continue
    const [id, rawOpacity] = token.split(':')
    const layer = catalogue.layers.find((l) => l.id === id)
    if (!layer || layer.kind === 'boundary' || layer.status !== 'ready') {
      dropped.push(`layer "${id}"`)
      continue
    }
    if (layers.some((l) => l.id === id)) {
      dropped.push(`layer "${id}" (repeated)`)
      continue
    }
    let opacity = layer.default_opacity
    if (rawOpacity !== undefined && rawOpacity !== '') {
      const parsed = Number(rawOpacity)
      if (Number.isFinite(parsed) && parsed >= 0 && parsed <= 1) opacity = parsed
      else dropped.push(`opacity "${rawOpacity}" for layer "${id}"`)
    }
    layers.push({ id, opacity, hidden: false })
  }

  for (const id of (params.get('hidden') ?? '').split(',')) {
    if (!id) continue
    const active = layers.find((l) => l.id === id)
    if (active) active.hidden = true
    else dropped.push(`hidden layer "${id}"`)
  }

  let place: string | null = null
  const rawPlace = params.get('place')
  if (rawPlace && rawPlace !== COUNTRY_ID) {
    if (places.some((p) => p.id === rawPlace)) place = rawPlace
    else dropped.push(`place "${rawPlace}"`)
  }

  const view: View = { section, layers, place, year: null }
  const rawYear = params.get('year')
  if (rawYear) {
    const year = Number(rawYear)
    const range = timeRange(view, catalogue)
    if (Number.isInteger(year) && range && year >= range.first && year <= range.last) view.year = year
    else dropped.push(`year "${rawYear}"`)
  }

  return { view, dropped }
}
