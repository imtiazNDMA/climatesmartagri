import { COUNTRY_ID, type Catalogue, type Place, type YearRange } from '../api/types'
import type { View } from './viewState'

/** The time slider's range: the widest span across the open section and every active layer. */
export function timeRange(view: View, catalogue: Catalogue): YearRange | null {
  const ranges: YearRange[] = []
  const section = catalogue.sections.find((s) => s.id === view.section)
  if (section?.years) ranges.push(section.years)
  for (const active of view.layers) {
    const layer = catalogue.layers.find((l) => l.id === active.id)
    if (layer?.years) ranges.push(layer.years)
  }
  if (!ranges.length) return null
  return {
    first: Math.min(...ranges.map((r) => r.first)),
    last: Math.max(...ranges.map((r) => r.last)),
  }
}

/** The year a layer or section actually shows: its nearest available year. */
export function effectiveYear(years: YearRange | null | undefined, year: number | null): number | null {
  if (!years) return null
  if (year === null) return years.last
  return Math.min(years.last, Math.max(years.first, year))
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
