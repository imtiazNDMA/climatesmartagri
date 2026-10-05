import type { FeatureCollection } from 'geojson'

export interface YearRange {
  first: number
  last: number
}

export interface LegendItem {
  colour: string
  label: string
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
  kind: 'raster' | 'vector' | 'boundary'
  status: 'ready' | 'no-data'
  legend: Legend | null
  years: YearRange | null
  default_opacity: number
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
  value: number | string
  unit: string
}

export interface SectionData {
  section_id: string
  place_id: string
  level_used: PlaceLevel
  year: number | null
  figures: Figure[]
  charts: unknown[]
}

export interface Boundaries {
  province: FeatureCollection | null
  district: FeatureCollection | null
}

export const COUNTRY_ID = 'PK'
