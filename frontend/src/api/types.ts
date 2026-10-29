import type { FeatureCollection } from 'geojson'

export interface YearRange {
  first: number
  last: number
  /** Exact observations when the series is not assumed to contain every intervening year. */
  available?: number[] | null
}

export interface RasterProduct {
  provider: string
  collection: string
  version: string
  resolution_metres: number
  area_unit: string
  nodata_value: string
}

export interface LegendItem {
  colour: string
  label: string
  /** For a shape layer: the feature property value this colour stands for. */
  value?: string | null
}

export type Legend =
  | { type: 'classes'; items: LegendItem[] }
  | {
      type: 'ramp'
      colours: string[]
      min: number
      max: number
      unit: string
      /** The value the middle colour stands for, when the ramp runs both ways from a neutral point. */
      mid?: number | null
      /** What each end of the ramp means, when the numbers alone do not say. */
      min_label?: string
      max_label?: string
    }

export type SectionStatus = 'ready' | 'no-data' | 'coming-soon'
export type PlaceLevel = 'national' | 'province' | 'district'

export interface Section {
  id: string
  title: string
  icon: string
  order: number
  status: SectionStatus
  /** A forecast section takes its layers from the forecast layer list rather than the catalogue's. */
  kind?: 'standard' | 'forecast' | 'crop-classification' | 'hazards'
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
  /** Where a raster has data (west, south, east, north); the map asks for no tiles beyond it. */
  bounds?: [number, number, number, number] | null
  /** Stable source semantics for a categorical product; concrete raster files stay server-side. */
  product?: RasterProduct | null
  /** Where the tiles come from: left out, a converted file; "mpc", the annual observation. */
  tile_source?: 'mpc' | null
}

/** One annual land-classification observation: the tiles for a year and where they came from. */
export interface LandCoverObservation {
  year: number
  collection: string
  /** The MPC mosaic registered over exactly item_ids. */
  search_id: string
  item_ids: string[]
  /** One tile URL template per layer drawn from the observation, keyed by layer id. */
  tiles: Record<string, string>
  bounds: [number, number, number, number]
  attribution: string
}

export interface ForecastLayer {
  id: string
  title: string
  group: string
  unit: string
  colours: string[]
  /** The values the two ends of the colours stand for. */
  min: number
  max: number
  /** A different pair of end values at some pressure levels, by level. */
  ranges: Record<string, [number, number]>
  /** A pair of end values of its own for some models, by model id; it wins over a level's pair. */
  model_ranges?: Record<string, [number, number]>
  /** The value each colour sits at, when the colours are not spread evenly between min and max. */
  stops?: number[] | null
  /** The pressure levels each model offers, by model id; 0 is the surface. Empty: no current data. */
  levels: Record<string, number[]>
}

export interface ForecastCatalogue {
  /** False when the server has no account for the forecast source. */
  configured: boolean
  /** West, south, east, north: the area forecasts are kept for. No tiles exist outside it. */
  bbox: [number, number, number, number]
  models: { id: string; label: string }[]
  groups: { id: string; title: string }[]
  layers: ForecastLayer[]
}

/** A time a forecast layer can be shown for and the model run it comes from, both UTC as YYYYMMDDHH. */
export interface ForecastTime {
  time: string
  run: string
}

export interface Catalogue {
  basemap_style_url: string
  sections: Section[]
  layers: Layer[]
  forecast?: ForecastCatalogue | null
}

export type Crop = 'Rice' | 'Maize' | 'Cotton' | 'Wheat' | 'Sugarcane'

export interface CropPrediction {
  label_index: number
  canonical_class_id: string
  canonical_class: string
  crop: Crop
  category: 'disease' | 'pest' | 'healthy'
  confidence: number
}

/** What to look for and how to prevent it; treatment steps stay empty until an agronomist reviews the guide. */
export interface CropGuidance {
  name: string
  type: string
  symptoms: string[]
  prevention: string[]
  treatment_steps: string[]
  reviewed: boolean
  version: string
  source: string
}

export interface CropClassificationResult {
  predictions: CropPrediction[]
  needs_expert_review: boolean
  model: string
  /** False until the model's confidence is calibrated: its percentages are rough. */
  calibrated: boolean
  /** For the most likely class; null when there is no guidance for it yet. */
  guidance: CropGuidance | null
}

export interface HazardBand {
  severity: string
  label: string
  threshold: number
  colour: string
}

export interface HazardProduct {
  id: string
  title: string
  forecast_layer: string
  unit: string
  direction: 'above' | 'below'
  district_percentile: number
  summary: string
  bands: HazardBand[]
}

export interface HazardCatalogue {
  classification: 'forecast-guidance'
  threshold_version: string
  disclaimer: string
  products: HazardProduct[]
}

export type DistrictRiskLevel = 'low' | 'medium' | 'high'

export interface DistrictRiskResponse {
  hazard: string
  forecast_layer: string
  time: string
  run: string
  unit: string
  threshold_version: string
  statistic: { percentile: number; label: string }
  colours: Record<DistrictRiskLevel, string>
  districts: { id: string; name: string; value: number; risk: DistrictRiskLevel | null }[]
}

export interface AssistantOverview {
  title: string
  summary: string
  model: string
  local_model: boolean
  sections: { id: string; title: string; summary: string; status: string }[]
  suggested_questions: string[]
}

export type AssistantTourAction = { type: 'open-section'; section_id: string }

export interface AssistantTourStep {
  id: string
  title: string
  body: string
  action?: AssistantTourAction
  camera: StoryCamera
}

export interface StoryCamera {
  center: [number, number]
  zoom: number
  bearing: number
  pitch: number
  duration: number
}

export interface AssistantTour {
  steps: AssistantTourStep[]
}

/** A view change the assistant asked the portal to apply. Only known types are ever sent. */
export type PortalAction =
  | { type: 'open-section'; section_id: string }
  | { type: 'select-place'; place_id: string }
  | { type: 'set-year'; year: number }
  | { type: 'toggle-layer'; layer_id: string; default_opacity: number }
  | {
      type: 'set-forecast'
      forecast: { layer: string; model: string; level: number; time: string | null }
    }

export interface AssistantChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface AssistantChatResponse {
  answer: string
  /** Fact source ids, for tracing and evaluation. */
  sources: string[]
  /** Readable names of the same sources, for readers. */
  source_names: string[]
  model: string
  grounded: boolean
  unchecked_numbers: number[]
  tool_calls: number
  /** View changes the model requested; the panel applies the ones it recognises. */
  portal_actions?: PortalAction[]
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
  /** The part of a whole this figure makes up, in percent, when it is one. */
  share?: number | null
  /** That whole in a few words, to read after the percentage: "of equipped land". */
  share_of?: string
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
  /** The series' own colour, when it stands for something that has one on the map. */
  colour?: string
}

/** A crop's dates: month ranges counted from 0 (start of January) to 12, and the original wording. */
export interface CalendarDates {
  text: string
  sowing: number[][]
  harvest: number[][]
}

export interface CalendarRow {
  crop: string
  traditional: CalendarDates
  adjusted: CalendarDates
  changed: boolean
  sown_earlier: boolean
  reason: string
}

export interface ChartSpec {
  id: string
  title: string
  /** How to read the chart, in a sentence or two. */
  kind: 'line' | 'stacked-area' | 'bar' | 'calendar' | 'shares' | 'diverging' | 'counts' | 'balance' | 'outlook' | 'explorer' | 'grid'
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
  /** For a calendar chart: one row per crop. */
  rows?: CalendarRow[]
  /** For a chart of the parts of a whole: the parts, largest first. */
  cells?: WaffleCell[]
  /** Where the value axis starts and ends, when it should not start at zero. */
  axis_min?: number
  axis_max?: number
  /** Bar series are laid end to end in one bar per category, not side by side. */
  stacked?: boolean
  /** Words written at the end of each bar, one per category. */
  bar_notes?: string[]
  /** The whole text at the end of each bar, in place of its value. */
  bar_labels?: string[]
  /** What a bar's tooltip says, a line per 
. */
  bar_details?: string[]
  /** Charts with the same group share one card, switched between by their group labels. */
  group?: string
  group_label?: string
  /** The bars the headline is about; the others are drawn fainter. */
  highlights?: number[]
  /** No numbers along the value axis: the bars are labelled themselves. */
  hide_axis?: boolean
  /** Drawn in once and left still, for bars whose lengths are being compared. */
  still?: boolean
  /** For a chart of two opposed shares: what the sides are, and the rows. */
  sides?: [ChartSide, ChartSide]
  splits?: DivergingSplit[]
  /** For a balance played through the years: the two amounts behind each balance, and the words for its two sides. */
  balance?: {
    available?: number[]
    needed?: number[][]
    negative?: string
    positive?: string
    zero?: string
    negative_word?: string
    positive_word?: string
    caption?: string
  }
  /**
   * For the water charts: the irrigation efficiencies the reader can choose between, in percent. The second
   * series is the water crops need at `base`; `given` are the efficiencies the source itself has figures for.
   */
  efficiency?: { min: number; max: number; base: number; start: number; given: number[] }
  /** For a chart of counts: the things counted, and how many there were to count among. */
  items?: CountItem[]
  total?: number
}

export interface ChartSide {
  label: string
  colour: string
}

export interface DivergingSplit {
  name: string
  /** Percent on each side of the centre line. */
  left: number
  right: number
  /** How much the row stands for; heavier rows are drawn thicker. */
  weight: number
  highlight: boolean
}

export interface CountItem {
  /** A picture for the row, by name. */
  icon?: string
  name: string
  value: number
  highlight: boolean
}

export interface WaffleCell {
  label: string
  colour: string
  /** The part's true percentage of the whole. */
  share: number
  /** Its width out of a hundred when the parts are laid end to end; these always add up to a hundred. */
  squares: number
}

export interface SectionData {
  section_id: string
  place_id: string
  level_used: PlaceLevel
  year: number | null
  figures: Figure[]
  charts: ChartSpec[]
  notes?: string[]
  /** What changed against earlier observations, in sentences worked out by fixed rules. */
  insights?: Insight[]
}

export interface Insight {
  comparison: 'previous' | 'baseline'
  from_year: number
  to_year: number
  rule: string
  class?: string
  text: string
  values: { label: string; value: number; unit: string }[]
}

export interface Boundaries {
  province: FeatureCollection | null
  district: FeatureCollection | null
}

export const COUNTRY_ID = 'PK'
