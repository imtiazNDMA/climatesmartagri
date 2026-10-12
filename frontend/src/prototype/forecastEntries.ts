// PROTOTYPE — throwaway. Three variants of the Weather forecast sidebar, switchable from a floating bar
// (or ?variant=A|B|C) on the real portal. This file is the data shaping the three share; none of the layout.
import { useSyncExternalStore } from 'react'
import type { ForecastCatalogue, ForecastLayer } from '../api/types'
import type { ForecastTimesState } from '../data/useForecastTimes'
import {
  chooseLayer, chooseModel, formatRun, formatTime, hasData, levelsFor, type ForecastChoice,
} from '../forecast/choice'
import { useUi } from '../state/uiState'
import { useView, viewStore } from '../state/viewState'

/** One thing to pick in the list. Several layers that are the same quantity cut differently share one entry. */
export interface Entry {
  id: string
  title: string
  group: string
  /** What the choosers within the entry are called: "Kind", "Period". Empty for an entry of one layer. */
  axes: string[]
  options: { layer: ForecastLayer; labels: string[] }[]
  preferred?: string
}

const FAMILIES: { id: string; title: string; axes: string[]; preferred?: string; members: [string, ...string[]][] }[] = [
  {
    id: 'precipitation', title: 'Precipitation', axes: ['Kind', 'Period'], preferred: 'rain-24h',
    members: [
      ['rain-3h', 'All', '3h'], ['rain-6h', 'All', '6h'], ['rain-12h', 'All', '12h'], ['rain-24h', 'All', '24h'],
      ['rain-7d', 'All', '7 days'], ['rain-total', 'All', 'Since run'],
      ['rainfall-6h', 'Rain', '6h'], ['rainfall-12h', 'Rain', '12h'], ['rainfall-24h', 'Rain', '24h'],
      ['snowfall-6h', 'Snow', '6h'], ['snowfall-12h', 'Snow', '12h'], ['snowfall-24h', 'Snow', '24h'],
      ['sleet-6h', 'Sleet', '6h'], ['sleet-12h', 'Sleet', '12h'], ['sleet-24h', 'Sleet', '24h'],
    ],
  },
  {
    id: 'temperature', title: 'Temperature', axes: ['Measure'],
    members: [['temperature', 'Mean'], ['temperature-max', 'Daily max'], ['temperature-min', 'Daily min']],
  },
  {
    id: 'relative-humidity', title: 'Relative humidity', axes: ['Measure'],
    members: [['relative-humidity', 'Mean'], ['relative-humidity-max', 'Max'], ['relative-humidity-min', 'Min']],
  },
  {
    id: 'cloud', title: 'Cloud cover', axes: ['Layer'],
    members: [['cloud-total', 'Total'], ['cloud-high', 'High'], ['cloud-low', 'Low']],
  },
  {
    id: 'temperature-anomaly', title: 'Temperature anomaly', axes: ['Measure'],
    members: [['temperature-anomaly', 'Mean'], ['temperature-max-anomaly', 'Max'], ['temperature-min-anomaly', 'Min']],
  },
  {
    id: 'precipitation-anomaly', title: 'Precipitation anomaly', axes: ['Shown as'],
    members: [['precipitation-anomaly', 'mm per day'], ['precipitation-anomaly-percent', '% of normal']],
  },
]

/** The catalogue's layers as entries, and the titles of those PMD has no current data for, by group. */
export function buildEntries(forecast: ForecastCatalogue): { entries: Entry[]; unavailable: Record<string, string[]> } {
  const byId = new Map(forecast.layers.map((layer) => [layer.id, layer]))
  const inFamily = new Set(FAMILIES.flatMap((family) => family.members.map((member) => member[0])))
  const entries: Entry[] = []
  const unavailable: Record<string, string[]> = {}
  const placed = new Set<string>()
  for (const layer of forecast.layers) {
    if (!hasData(layer)) {
      ;(unavailable[layer.group] ??= []).push(layer.title)
      continue
    }
    if (!inFamily.has(layer.id)) {
      entries.push({ id: layer.id, title: layer.title, group: layer.group, axes: [], options: [{ layer, labels: [] }] })
      continue
    }
    const family = FAMILIES.find((f) => f.members.some((member) => member[0] === layer.id))!
    if (placed.has(family.id)) continue
    placed.add(family.id)
    const options = family.members.flatMap(([id, ...labels]) => {
      const member = byId.get(id)
      return member && hasData(member) ? [{ layer: member, labels }] : []
    })
    entries.push({
      id: family.id, title: family.title, group: layer.group, axes: family.axes, options, preferred: family.preferred,
    })
  }
  return { entries, unavailable }
}

export const entryOf = (entries: Entry[], layerId: string | undefined) =>
  entries.find((entry) => entry.options.some((option) => option.layer.id === layerId))

/** The values an axis offers, in order, each marked by whether it can be combined with the other axis as it stands. */
export function axisValues(entry: Entry, axis: number, current: string[] | undefined) {
  const values = [...new Set(entry.options.map((option) => option.labels[axis]))]
  return values.map((value) => ({
    value,
    on: current?.[axis] === value,
    fits: entry.options.some(
      (option) => option.labels[axis] === value && option.labels.every((l, i) => i === axis || !current || l === current[i]),
    ),
  }))
}

/** Everything a variant needs to show and change the forecast on the map. */
export function usePick(forecast: ForecastCatalogue, entries: Entry[], times: ForecastTimesState) {
  const choice = useView((s) => s.forecast)
  const fetching = useUi((s) => s.forecastLoading)
  const tileError = useUi((s) => s.layerErrors.forecast ?? false)
  const layer = forecast.layers.find((l) => l.id === choice?.layer)
  const entry = entryOf(entries, choice?.layer)
  const labels = entry?.options.find((option) => option.layer.id === choice?.layer)?.labels
  const set = (next: ForecastChoice | null) => viewStore.getState().setForecast(next)
  const slot = times.status === 'ready' ? times.times.find((t) => t.time === choice?.time) : undefined

  let status: string | null = null
  if (!choice) status = null
  else if (times.status === 'loading') status = 'Asking PMD which times it has…'
  else if (times.status === 'ready' && times.times.length === 0) status = 'PMD has no recent files for this choice.'
  else if (times.status === 'error') {
    status = times.reason === 'source-unreachable' ? 'PMD’s server is not answering.' : 'The forecast could not be loaded.'
  } else if (tileError) status = 'This time could not be fetched from PMD.'
  else if (fetching) status = 'Fetching this time from PMD…'

  return {
    choice,
    layer,
    entry,
    labels,
    status,
    when: slot ? formatTime(slot.time) : null,
    run: slot ? formatRun(slot.run) : null,
    models: layer
      ? forecast.models.map((model) => ({ ...model, offers: levelsFor(layer, model.id).length > 0, on: choice?.model === model.id }))
      : [],
    levels: layer && choice ? levelsFor(layer, choice.model) : [],
    pickEntry: (target: Entry) => {
      if (target.id === entry?.id) return set(null)
      const first = target.options.find((option) => option.layer.id === target.preferred) ?? target.options[0]
      set(chooseLayer(forecast, first.layer.id, choice))
    },
    pickAxis: (axis: number, value: string) => {
      if (!entry) return
      const wanted = (labels ?? []).map((l, i) => (i === axis ? value : l))
      const exact = entry.options.find((option) => option.labels.every((l, i) => l === wanted[i]))
      const near = exact ?? entry.options.find((option) => option.labels[axis] === value)
      if (near) set(chooseLayer(forecast, near.layer.id, choice))
    },
    pickModel: (modelId: string) => layer && set(chooseModel(layer, modelId, choice)),
    pickLevel: (level: number) => choice && set({ ...choice, level }),
    clear: () => set(null),
  }
}

export type Pick = ReturnType<typeof usePick>

// --- which variant is on screen: kept for the tab, started from ?variant=

export const VARIANTS = [
  { key: 'current', name: 'Current panel' },
  { key: 'A', name: 'Refined list' },
  { key: 'B', name: 'Card deck' },
  { key: 'C', name: 'Dark console' },
] as const
export type VariantKey = (typeof VARIANTS)[number]['key']

const STORE_KEY = 'csa-prototype-forecast-variant'
const listeners = new Set<() => void>()
const fromUrl = new URLSearchParams(window.location.search).get('variant')
if (fromUrl && VARIANTS.some((v) => v.key === fromUrl)) sessionStorage.setItem(STORE_KEY, fromUrl)

const read = () => (sessionStorage.getItem(STORE_KEY) ?? 'A') as VariantKey

export function setVariant(key: VariantKey) {
  sessionStorage.setItem(STORE_KEY, key)
  listeners.forEach((listener) => listener())
}

export function useVariant(): VariantKey {
  return useSyncExternalStore((listener) => {
    listeners.add(listener)
    return () => listeners.delete(listener)
  }, read)
}
