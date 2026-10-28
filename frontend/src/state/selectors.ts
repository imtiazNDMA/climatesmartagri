import { COUNTRY_ID, type Catalogue, type Place, type YearRange } from '../api/types'
import type { View } from './viewState'

/** The years a range actually has observations for: the ones it lists, or every year it spans. */
export function rangeObservations(years: YearRange | null | undefined): number[] {
  if (!years) return []
  if (years.available) return [...years.available]
  return Array.from({ length: years.last - years.first + 1 }, (_, i) => years.first + i)
}

/** The observation nearest a year; when two are equally near, the earlier one. */
export function nearestObservation(observations: number[], year: number): number {
  let best = observations[0]
  for (const candidate of observations) {
    if (Math.abs(candidate - year) < Math.abs(best - year)) best = candidate
  }
  return best
}

/** The slider's observations: every year the visible temporal content can show, once each. */
export function timeObservations(view: View, catalogue: Catalogue): number[] {
  const seen = new Set<number>()
  const section = catalogue.sections.find((s) => s.id === view.section)
  if (section?.years) for (const year of rangeObservations(section.years)) seen.add(year)
  for (const active of view.layers) {
    const layer = catalogue.layers.find((l) => l.id === active.id)
    if (layer?.years) for (const year of rangeObservations(layer.years)) seen.add(year)
  }
  return [...seen].sort((a, b) => a - b)
}

/** Where a year sits in the observation list; the last one when no year has been chosen. */
export function observationIndex(observations: number[], year: number | null): number {
  if (!observations.length) return -1
  if (year === null) return observations.length - 1
  let best = 0
  for (let i = 1; i < observations.length; i += 1) {
    if (Math.abs(observations[i] - year) < Math.abs(observations[best] - year)) best = i
  }
  return best
}

/** The observation playback goes to after this year: the next one, or the first after the last. */
export function nextObservation(observations: number[], year: number | null): number | null {
  if (!observations.length) return null
  const at = observationIndex(observations, year)
  return observations[at + 1 >= observations.length ? 0 : at + 1]
}

/** The year a layer or section actually shows: its nearest available year. */
export function effectiveYear(years: YearRange | null | undefined, year: number | null): number | null {
  const observations = rangeObservations(years)
  if (!observations.length) return null
  if (year === null) return observations[observations.length - 1]
  return nearestObservation(observations, year)
}

/** The stored year, kept only while something on screen has years, and on one of them. */
export function tidyYear(view: View, catalogue: Catalogue): number | null {
  const observations = timeObservations(view, catalogue)
  if (!observations.length || view.year === null) return null
  return nearestObservation(observations, view.year)
}

export function sectionsWithActiveLayers(view: View, catalogue: Catalogue): Set<string> {
  const result = new Set<string>()
  for (const active of view.layers) {
    const sectionId = catalogue.layers.find((l) => l.id === active.id)?.section_id
    if (sectionId) result.add(sectionId)
  }
  return result
}

/** The breadcrumb trail: country first, selection last. */
export function ancestors(places: Place[], placeId: string | null): Place[] {
  const byId = new Map(places.map((p) => [p.id, p]))
  const trail: Place[] = []
  let current = byId.get(placeId ?? COUNTRY_ID) ?? byId.get(COUNTRY_ID)
  while (current && !trail.includes(current)) {
    trail.unshift(current)
    current = current.parent_id ? byId.get(current.parent_id) : undefined
  }
  return trail
}

/**
 * What a click on a district selects: the province first, then the district
 * once its province is the selection, or the new province if it is elsewhere.
 */
export function clickTarget(places: Place[], selectedId: string | null, clickedDistrictId: string): string | null {
  const byId = new Map(places.map((p) => [p.id, p]))
  const district = byId.get(clickedDistrictId)
  if (!district) return null
  const province = district.parent_id ? byId.get(district.parent_id) : undefined
  if (!province) return district.id
  const selected = selectedId ? byId.get(selectedId) : undefined
  const selectedProvinceId = selected?.level === 'district' ? selected.parent_id : selected?.id
  return selectedProvinceId === province.id ? district.id : province.id
}

export function searchPlaces(places: Place[], query: string, limit = 8): Place[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return []
  const matches = places.filter((p) => p.level !== 'national' && p.name.toLowerCase().includes(needle))
  const startsWith = (p: Place) => (p.name.toLowerCase().startsWith(needle) ? 0 : 1)
  return matches.sort((a, b) => startsWith(a) - startsWith(b) || a.name.localeCompare(b.name)).slice(0, limit)
}
