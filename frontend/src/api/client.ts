import type { FeatureCollection } from 'geojson'
import type {
  Catalogue,
  AssistantChatMessage,
  AssistantChatResponse,
  AssistantOverview,
  AssistantTour,
  Crop,
  CropClassificationResult,
  DistrictRiskResponse,
  ForecastTime,
  HazardCatalogue,
  LandCoverObservation,
  Layer,
  Place,
  SectionData,
} from './types'

export class ApiError extends Error {
  status: number
  reason: string | null

  constructor(status: number, reason: string | null, message: string) {
    super(message)
    this.status = status
    this.reason = reason
  }
}

export class BackendUnreachableError extends Error {
  constructor() {
    super('The portal cannot reach its data service.')
  }
}

const GATEWAY_STATUSES = [502, 503, 504]

async function getJson<T>(path: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(path)
  } catch {
    throw new BackendUnreachableError()
  }
  if (GATEWAY_STATUSES.includes(response.status)) throw new BackendUnreachableError()
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = body && typeof body === 'object' ? (body as { detail?: unknown }).detail : null
    const shaped = detail && typeof detail === 'object' ? (detail as { message?: unknown; reason?: unknown }) : null
    throw new ApiError(
      response.status,
      typeof shaped?.reason === 'string' ? shaped.reason : null,
      typeof shaped?.message === 'string' ? shaped.message : `Request failed (${response.status})`,
    )
  }
  return (await response.json()) as T
}

async function responseJson<T>(request: () => Promise<Response>): Promise<T> {
  let response: Response
  try {
    response = await request()
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new BackendUnreachableError()
  }
  if (GATEWAY_STATUSES.includes(response.status)) {
    const body = await response.clone().json().catch(() => null)
    const detail = body && typeof body === 'object' ? (body as { detail?: unknown }).detail : null
    if (!detail || typeof detail !== 'object') throw new BackendUnreachableError()
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = body && typeof body === 'object' ? (body as { detail?: unknown }).detail : null
    const shaped = detail && typeof detail === 'object' ? (detail as { message?: unknown; reason?: unknown }) : null
    throw new ApiError(
      response.status,
      typeof shaped?.reason === 'string' ? shaped.reason : null,
      typeof shaped?.message === 'string' ? shaped.message : `Request failed (${response.status})`,
    )
  }
  return (await response.json()) as T
}

export const fetchCatalogue = () => getJson<Catalogue>('/api/catalogue')
export const fetchPlaces = () => getJson<Place[]>('/api/places')
export const fetchHealth = () =>
  getJson<{
    status: string
    boundaries_loaded: boolean
    boundaries_error: string | null
    layers: Record<string, boolean>
  }>('/api/health')

export async function fetchBoundaries(level: 'province' | 'district'): Promise<FeatureCollection | null> {
  try {
    return await getJson<FeatureCollection>(`/api/places/boundaries?level=${level}`)
  } catch (error) {
    if (error instanceof ApiError && error.reason === 'no-data') return null
    throw error
  }
}

export function fetchSectionData(sectionId: string, placeId: string | null, year: number | null) {
  const params: string[] = []
  if (placeId) params.push(`place=${encodeURIComponent(placeId)}`)
  if (year !== null) params.push(`year=${year}`)
  const query = params.length ? `?${params.join('&')}` : ''
  return getJson<SectionData>(`/api/sections/${sectionId}/data${query}`)
}

export function classifyCropImage(image: File, crop: Crop, topK = 3) {
  const form = new FormData()
  form.append('image', image)
  form.append('crop', crop)
  form.append('top_k', String(topK))
  return responseJson<CropClassificationResult>(() =>
    fetch('/api/crop-classification/predict', { method: 'POST', body: form }),
  )
}

export function fetchHazardProducts() {
  return getJson<HazardCatalogue>('/api/hazards/products')
}

export const fetchAssistantOverview = () => getJson<AssistantOverview>('/api/assistant/overview')

export const fetchAssistantTour = () => getJson<AssistantTour>('/api/assistant/tour')

export function askAssistant(
  question: string,
  history: AssistantChatMessage[],
  view: {
    section_id: string | null
    place_id: string | null
    year: number | null
    active_layer_ids: string[]
    forecast: { layer: string; model: string; level: number; time: string | null } | null
    district_risk: {
      hazard: string
      statistic: string
      time: string
      run: string
      districts: { id: string; name: string; value: number; risk: 'low' | 'medium' | 'high' | null }[]
    } | null
  },
  signal?: AbortSignal,
) {
  return responseJson<AssistantChatResponse>(() =>
    fetch('/api/assistant/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, history: history.slice(-8), view }),
      signal,
    }),
  )
}

interface ForecastAddress {
  layer: string
  model: string
  level: number
}

export function fetchDistrictRisk(
  hazard: string,
  choice: ForecastAddress,
  time: string,
  run: string,
): Promise<DistrictRiskResponse> {
  const params = new URLSearchParams({
    hazard,
    model: choice.model,
    level: String(choice.level),
    time,
    run,
  })
  return getJson<DistrictRiskResponse>(`/api/hazards/district-risk?${params}`)
}

const forecastQuery = ({ layer, model, level }: ForecastAddress) => `layer=${layer}&model=${model}&level=${level}`

/** The times a forecast layer can be shown for, earliest first. */
export async function fetchForecastTimes(choice: ForecastAddress): Promise<ForecastTime[]> {
  return (await getJson<{ times: ForecastTime[] }>(`/api/forecast/times?${forecastQuery(choice)}`)).times
}

/**
 * Where a forecast layer's tiles are for one time, smoothed between the model's grid points. The address
 * names the model run, so what it answers can never change and the browser keeps it without asking again.
 */
export function forecastTileUrl(choice: ForecastAddress, time: string, run: string): string {
  const query = `${forecastQuery(choice)}&time=${time}&run=${run}&resampling=bilinear&reproject=bilinear`
  return `/api/forecast/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?${query}`
}

/**
 * Ask the backend to get a forecast time ready, without waiting for the answer. The first request for a
 * time has to fetch it from PMD, so asking ahead of the slider keeps playback from stalling.
 */
export function warmForecast(choice: ForecastAddress, time: string, run: string): void {
  fetch(`/api/forecast/cog/info?${forecastQuery(choice)}&time=${time}&run=${run}`).catch(() => {})
}

export function tileUrlTemplate(layerId: string, year: number | null, retry: number): string {
  const params: string[] = []
  if (year !== null) params.push(`year=${year}`)
  if (retry > 0) params.push(`r=${retry}`)
  const query = params.length ? `?${params.join('&')}` : ''
  return `/api/tiles/${layerId}/{z}/{x}/{y}${query}`
}

/** Where the annual land-classification observation for a year is asked for. */
export function landCoverObservationUrl(year: number | null, retry: number): string {
  const params: string[] = []
  if (year !== null) params.push(`year=${year}`)
  if (retry > 0) params.push(`r=${retry}`)
  const query = params.length ? `?${params.join('&')}` : ''
  return `/api/land-cover/observation${query}`
}

const observations = new Map<string, Promise<LandCoverObservation>>()

/**
 * A year's land-classification observation. Each is asked for once, so going back to a year, or to one
 * fetched in advance during playback, is immediate; a failed request is forgotten so it can be retried.
 */
export function fetchLandCoverObservation(
  year: number | null,
  retry: number,
): Promise<LandCoverObservation> {
  const url = landCoverObservationUrl(year, retry)
  // The latest year is whatever the server says it is, so only a named year is kept.
  if (year === null) return getJson<LandCoverObservation>(url)
  let found = observations.get(url)
  if (!found) {
    found = getJson<LandCoverObservation>(url)
    found.catch(() => observations.delete(url))
    observations.set(url, found)
  }
  return found
}

/** Where a raster or vector layer's tiles are: its own address if the catalogue gives one. */
export function layerTileUrl(
  layer: Pick<Layer, 'id' | 'kind' | 'tile_url'>,
  year: number | null,
  retry: number,
): string {
  if (!layer.tile_url) return tileUrlTemplate(layer.id, year, retry)
  if (retry <= 0) return layer.tile_url
  return `${layer.tile_url}${layer.tile_url.includes('?') ? '&' : '?'}r=${retry}`
}

export function layerGeojsonUrl(layerId: string, retry: number): string {
  return `/api/layers/${layerId}/geojson${retry > 0 ? `?r=${retry}` : ''}`
}

/** Learn whether a layer's data can be served: its shapes for a shape layer, its root tile otherwise. */
export async function probeLayer(
  layer: Pick<Layer, 'id' | 'kind' | 'tile_url' | 'tile_source'>,
  year: number | null,
  retry: number,
): Promise<boolean> {
  const address =
    layer.kind === 'geojson'
      ? layerGeojsonUrl(layer.id, retry)
      : layer.tile_source === 'mpc'
        ? landCoverObservationUrl(year, retry)
        : layerTileUrl(layer, year, retry).replace('{z}/{x}/{y}', '0/0/0')
  try {
    return (await fetch(address)).ok
  } catch {
    return false
  }
}

/** Ask for the root tile to learn whether a layer's tiles can be served at all. */
export async function probeTile(layerId: string, year: number | null, retry: number): Promise<boolean> {
  try {
    const response = await fetch(tileUrlTemplate(layerId, year, retry).replace('{z}/{x}/{y}', '0/0/0'))
    return response.ok
  } catch {
    return false
  }
}

/** Run a request again while the backend is unreachable, for a backend that is still starting. */
export async function withRetry<T>(run: () => Promise<T>, attempts: number, delayMs: number): Promise<T> {
  for (let attempt = 1; ; attempt += 1) {
    try {
      return await run()
    } catch (error) {
      if (!(error instanceof BackendUnreachableError) || attempt >= attempts) throw error
      await new Promise((resolve) => setTimeout(resolve, delayMs))
    }
  }
}
