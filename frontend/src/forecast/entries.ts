import type { ForecastCatalogue, ForecastLayer } from '../api/types'
import { hasData } from './choice'

/**
 * One thing to pick in the forecast panel. Layers that are the same quantity cut different ways (rain over
 * 6 hours or 24, temperature as mean or maximum) share an entry and are told apart by its choosers.
 */
export interface Entry {
  id: string
  title: string
  group: string
  /** What the choosers within the entry are called: "Kind", "Period". None for an entry of one layer. */
  axes: string[]
  /** The layers, each with its label on every axis, in the order the choosers show them. */
  options: { layer: ForecastLayer; labels: string[] }[]
  /** The layer shown when the entry is first picked, if not its first. */
  preferred?: string
}

/** The layers that belong together. Each member is a layer id followed by its label on each axis. */
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
    id: 'cloud-cover', title: 'Cloud cover', axes: ['Layer'],
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

/**
 * The catalogue's layers as entries, in catalogue order, and the titles of the layers PMD has no current
 * data for, by group. A family with only one layer on offer is an entry of that layer under its own title.
 */
export function buildEntries(forecast: ForecastCatalogue): { entries: Entry[]; unavailable: Record<string, string[]> } {
  const byId = new Map(forecast.layers.map((layer) => [layer.id, layer]))
  const entries: Entry[] = []
  const unavailable: Record<string, string[]> = {}
  const placed = new Set<string>()
  for (const layer of forecast.layers) {
    if (!hasData(layer)) {
      ;(unavailable[layer.group] ??= []).push(layer.title)
      continue
    }
    const family = FAMILIES.find((f) => f.members.some(([id]) => id === layer.id))
    const options = (family?.members ?? []).flatMap(([id, ...labels]) => {
      const member = byId.get(id)
      return member && hasData(member) ? [{ layer: member, labels }] : []
    })
    if (!family || options.length < 2) {
      entries.push({ id: layer.id, title: layer.title, group: layer.group, axes: [], options: [{ layer, labels: [] }] })
    } else if (!placed.has(family.id)) {
      placed.add(family.id)
      entries.push({
        id: family.id, title: family.title, group: layer.group, axes: family.axes, options, preferred: family.preferred,
      })
    }
  }
  return { entries, unavailable }
}

/** The entry a layer belongs to. */
export function entryOf(entries: Entry[], layerId: string | undefined): Entry | undefined {
  return entries.find((entry) => entry.options.some((option) => option.layer.id === layerId))
}

/** The layer an entry shows when it is first picked. */
export function firstLayer(entry: Entry): ForecastLayer {
  return (entry.options.find((option) => option.layer.id === entry.preferred) ?? entry.options[0]).layer
}

export interface AxisValue {
  value: string
  /** True for the value the layer on the map has. */
  on: boolean
  /** False when no layer has this value together with the other axes as they stand; picking it changes those too. */
  fits: boolean
}

/** The values one of an entry's choosers offers, in order. `current` is the labels of the layer on the map. */
export function axisValues(entry: Entry, axis: number, current: string[] | undefined): AxisValue[] {
  const values = [...new Set(entry.options.map((option) => option.labels[axis]))]
  return values.map((value) => ({
    value,
    on: current?.[axis] === value,
    fits: entry.options.some(
      (option) => option.labels[axis] === value && option.labels.every((l, i) => i === axis || !current || l === current[i]),
    ),
  }))
}

/**
 * The layer to move to when one chooser changes: the one with that value and the other axes unchanged,
 * or failing that the first with that value.
 */
export function layerForAxis(entry: Entry, current: string[] | undefined, axis: number, value: string): ForecastLayer | undefined {
  const wanted = (current ?? []).map((label, i) => (i === axis ? value : label))
  const exact = entry.options.find((option) => option.labels.every((label, i) => label === wanted[i]))
  return (exact ?? entry.options.find((option) => option.labels[axis] === value))?.layer
}
