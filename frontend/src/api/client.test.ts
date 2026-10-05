import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  BackendUnreachableError,
  fetchBoundaries,
  fetchCatalogue,
  fetchSectionData,
  layerGeojsonUrl,
  probeLayer,
  probeTile,
  tileUrlTemplate,
  withRetry,
} from './client'

function respond(status: number, body: unknown) {
  return vi.fn(async (_url: string) => new Response(body === null ? null : JSON.stringify(body), { status }))
}

afterEach(() => vi.unstubAllGlobals())

describe('client', () => {
  it('returns parsed JSON on success', async () => {
    vi.stubGlobal('fetch', respond(200, { sections: [], layers: [], basemap_style_url: 'x' }))
    expect((await fetchCatalogue()).basemap_style_url).toBe('x')
  })

  it('throws BackendUnreachableError when fetch rejects', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('failed') }))
    await expect(fetchCatalogue()).rejects.toBeInstanceOf(BackendUnreachableError)
  })

  it.each([502, 503, 504])('throws BackendUnreachableError on %i', async (status) => {
    vi.stubGlobal('fetch', respond(status, { detail: { message: 'x', reason: 'unreachable' } }))
    await expect(fetchCatalogue()).rejects.toBeInstanceOf(BackendUnreachableError)
  })

  it('throws ApiError carrying status, reason and message', async () => {
    vi.stubGlobal('fetch', respond(404, { detail: { message: 'Unknown section', reason: 'not-found' } }))
    const error = await fetchSectionData('ghost', null, null).catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(404)
    expect(error.reason).toBe('not-found')
    expect(error.message).toBe('Unknown section')
  })

  it('copes with error bodies that are not the expected shape', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('Internal Server Error', { status: 500 })))
    const error = await fetchCatalogue().catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.reason).toBeNull()
  })

  it('returns null boundaries when they are not loaded', async () => {
    vi.stubGlobal('fetch', respond(404, { detail: { message: 'none', reason: 'no-data' } }))
    expect(await fetchBoundaries('province')).toBeNull()
  })

  it('builds section data URLs, omitting absent values', async () => {
    const fetchMock = respond(200, {})
    vi.stubGlobal('fetch', fetchMock)
    await fetchSectionData('alpha-section', null, null)
    await fetchSectionData('alpha-section', 'PK1', 2005)
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual([
      '/api/sections/alpha-section/data',
      '/api/sections/alpha-section/data?place=PK1&year=2005',
    ])
  })

  it('builds tile URL templates', () => {
    expect(tileUrlTemplate('forest', null, 0)).toBe('/api/tiles/forest/{z}/{x}/{y}')
    expect(tileUrlTemplate('forest', 2005, 0)).toBe('/api/tiles/forest/{z}/{x}/{y}?year=2005')
    expect(tileUrlTemplate('forest', 2005, 2)).toBe('/api/tiles/forest/{z}/{x}/{y}?year=2005&r=2')
  })

  it('probes the root tile and reports success or failure', async () => {
    const ok = respond(200, null)
    vi.stubGlobal('fetch', ok)
    expect(await probeTile('forest', 2005, 0)).toBe(true)
    expect(ok.mock.calls[0][0]).toBe('/api/tiles/forest/0/0/0?year=2005')
    vi.stubGlobal('fetch', respond(404, { detail: { message: 'x', reason: 'no-data' } }))
    expect(await probeTile('forest', null, 0)).toBe(false)
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('failed') }))
    expect(await probeTile('forest', null, 0)).toBe(false)
  })
})

describe('withRetry', () => {
  it('tries again while the backend is unreachable, then returns the result', async () => {
    let calls = 0
    const result = await withRetry(async () => {
      calls += 1
      if (calls < 3) throw new BackendUnreachableError()
      return 'ok'
    }, 4, 1)
    expect(result).toBe('ok')
    expect(calls).toBe(3)
  })

  it('gives up after the allowed attempts', async () => {
    let calls = 0
    const run = async () => {
      calls += 1
      throw new BackendUnreachableError()
    }
    await expect(withRetry(run, 3, 1)).rejects.toBeInstanceOf(BackendUnreachableError)
    expect(calls).toBe(3)
  })

  it('does not retry other errors', async () => {
    let calls = 0
    const run = async () => {
      calls += 1
      throw new ApiError(404, 'not-found', 'nope')
    }
    await expect(withRetry(run, 3, 1)).rejects.toBeInstanceOf(ApiError)
    expect(calls).toBe(1)
  })
})

describe('shape layers', () => {
  const shapes = { id: 'shapes', kind: 'geojson' as const }
  const raster = { id: 'forest', kind: 'raster' as const }

  it('builds the data address, with the retry count when retrying', () => {
    expect(layerGeojsonUrl('shapes', 0)).toBe('/api/layers/shapes/geojson')
    expect(layerGeojsonUrl('shapes', 2)).toBe('/api/layers/shapes/geojson?r=2')
  })

  it('probes a shape layer at its data address and a tile layer at its root tile', async () => {
    const ok = respond(200, {})
    vi.stubGlobal('fetch', ok)
    expect(await probeLayer(shapes, 2005, 0)).toBe(true)
    expect(await probeLayer(raster, 2005, 0)).toBe(true)
    expect(ok.mock.calls.map((c) => c[0])).toEqual(['/api/layers/shapes/geojson', '/api/tiles/forest/0/0/0?year=2005'])
  })

  it('reports a shape layer that cannot be loaded', async () => {
    vi.stubGlobal('fetch', respond(404, { detail: { message: 'x', reason: 'no-data' } }))
    expect(await probeLayer(shapes, null, 0)).toBe(false)
  })
})
