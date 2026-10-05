import type { FeatureCollection } from 'geojson'
import type { Catalogue, Place, SectionData } from './types'

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
export const fetchHealth = () => getJson<{ status: string }>('/api/health')

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

/** Ask for the root tile to learn whether a layer's tiles can be served at all. */
export async function probeTile(layerId: string, year: number | null, retry: number): Promise<boolean> {
  try {
    const response = await fetch(tileUrlTemplate(layerId, year, retry).replace('{z}/{x}/{y}', '0/0/0'))
    return response.ok
  } catch {
    return false
  }
}
