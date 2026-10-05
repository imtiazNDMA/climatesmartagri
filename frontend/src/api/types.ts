import type { FeatureCollection } from 'geojson'

export interface YearRange {
  first: number
  last: number
}

export interface LegendItem {
  colour: string
  label: string
  /** For a shape layer: the feature property value this colour stands for. */
  value?: string | null
}

export type Legend =
  | { type: 'classes'; items: LegendItem[] }
  | { type: 'ramp'; colours: string[]; min: number; max: number; unit: string }

export type SectionStatus = 'ready' | 'no-data' | 'coming-soon'
export type PlaceLevel = 'national' | 'province' | 'district'

export interface Section {
  id: string
  title: string
  icon: string
  order: number
  status: SectionStatus
  summary: string
  place_levels: PlaceLevel[]
  years: YearRange | null
}

export interface Layer {
  id: string
  section_id: string | null
  title: string
  kind: 'raster' | 'vector' | 'geojson' | 'boundary'
  status: 'ready' | 'no-data'
  legend: Legend | null
  /** For a shape layer: the feature property the legend colours. */
  property?: string | null
  years: YearRange | null
  default_opacity: number
  /** For a raster served by TiTiler: where its tiles are, with {z}/{x}/{y} to fill in. */
  tile_url?: string | null
  /** The deepest zoom the data has detail for. */
  max_zoom?: number | null
}

export interface Catalogue {
  basemap_style_url: string
  sections: Section[]
  layers: Layer[]
}

export interface Place {
  id: string
  name: string
  level: PlaceLevel
  parent_id: string | null
  bbox: [number, number, number, number]
}

export interface Figure {
  label: string
  value: number | string | null
  unit: string
}

export interface ChartSeries {
  name: string
  /** Position in the fixed colour order, starting at 1. */
  slot: number
  values: (number | null)[]
  /** Indexes that get a dot, for charts that single out some points. */
  points?: number[]
  /** 'strong' draws the series darker and thicker: the one the story is about. */
  emphasis?: 'strong'
}

export interface ChartSpec {
  id: string
  title: string
  /** How to read the chart, in a sentence or two. */
  subtitle?: string
  kind: 'line' | 'stacked-area' | 'bar'
  unit: string
  /** True when the categories are years. */
  time: boolean
  categories: (string | number)[]
  series: ChartSeries[]
  horizontal?: boolean
  highlight?: number | null
  zero_line?: boolean
  note?: string
  /** Label each line where it ends, in the full view. */
  end_labels?: boolean
  /** Colour bars by whether they are below zero. */
  colour_by_sign?: boolean
  /** A colour slot per bar, when each bar is its own thing. */
  bar_slots?: number[]
  /** A colour per bar, for bars that stand for map layers and wear their colours. */
  bar_colours?: string[]
}

export interface SectionData {
  section_id: string
  place_id: string
  level_used: PlaceLevel
  year: number | null
  figures: Figure[]
  charts: ChartSpec[]
  notes?: string[]
}

export interface Boundaries {
  province: FeatureCollection | null
  district: FeatureCollection | null
}

export const COUNTRY_ID = 'PK'
