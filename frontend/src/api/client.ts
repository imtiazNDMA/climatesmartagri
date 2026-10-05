import type { FeatureCollection } from 'geojson'
import type { Catalogue, Layer, Place, SectionData } from './types'

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

export function tileUrlTemplate(layerId: string, year: number | null, retry: number): string {
  const params: string[] = []
  if (year !== null) params.push(`year=${year}`)
  if (retry > 0) params.push(`r=${retry}`)
  const query = params.length ? `?${params.join('&')}` : ''
  return `/api/tiles/${layerId}/{z}/{x}/{y}${query}`
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
  layer: Pick<Layer, 'id' | 'kind' | 'tile_url'>,
  year: number | null,
  retry: number,
): Promise<boolean> {
  const address =
    layer.kind === 'geojson'
      ? layerGeojsonUrl(layer.id, retry)
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
