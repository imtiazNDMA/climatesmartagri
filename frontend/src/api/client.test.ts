import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  BackendUnreachableError,
  classifyCropImage,
  askAssistant,
  fetchAssistantOverview,
  fetchAssistantTour,
  fetchDistrictRisk,
  fetchHazardProducts,
  fetchBoundaries,
  fetchCatalogue,
  fetchSectionData,
  layerGeojsonUrl,
  layerTileUrl,
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

  it('posts crop images as multipart form data', async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) =>
      new Response(JSON.stringify({ predictions: [], needs_expert_review: true, model: 'improved-002' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['leaf'], 'leaf.png', { type: 'image/png' })
    await classifyCropImage(file, 'Maize', 3)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/crop-classification/predict')
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('POST')
    const form = init.body as FormData
    expect(form.get('image')).toBe(file)
    expect(form.get('crop')).toBe('Maize')
    expect(form.get('top_k')).toBe('3')
  })

  it('fetches hazard guidance products', async () => {
    const fetchMock = respond(200, { classification: 'forecast-guidance', products: [] })
    vi.stubGlobal('fetch', fetchMock)
    await expect(fetchHazardProducts()).resolves.toMatchObject({ classification: 'forecast-guidance' })
    expect(fetchMock).toHaveBeenCalledWith('/api/hazards/products')
  })

  it('fetches the deterministic assistant overview and tour', async () => {
    const fetchMock = respond(200, { steps: [], sections: [] })
    vi.stubGlobal('fetch', fetchMock)
    await fetchAssistantOverview()
    await fetchAssistantTour()
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      '/api/assistant/overview',
      '/api/assistant/tour',
    ])
  })

  it('sends questions with bounded history and current portal context', async () => {
    const fetchMock = respond(200, {
      answer: 'Local answer', sources: ['fact:123'], source_names: ['Alpha / Pakistan'], model: 'qwen', grounded: false,
      unchecked_numbers: [999], tool_calls: 1,
    })
    vi.stubGlobal('fetch', fetchMock)
    const history = Array.from({ length: 10 }, (_, index) => ({
      role: (index % 2 ? 'assistant' : 'user') as 'assistant' | 'user',
      content: `Message ${index}`,
    }))
    await askAssistant('Explain this', history, {
      section_id: 'hazards', place_id: 'PK101', year: null, active_layer_ids: ['forest'],
      forecast: null, district_risk: null,
    })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/assistant/chat')
    expect(init.method).toBe('POST')
    const body = JSON.parse(init.body as string)
    expect(body.question).toBe('Explain this')
    expect(body.history).toHaveLength(8)
    expect(body.history[0].content).toBe('Message 2')
    expect(body.view).toMatchObject({ section_id: 'hazards', place_id: 'PK101' })
  })

  it('requests district risk for an exact forecast time and run', async () => {
    const fetchMock = respond(200, { districts: [] })
    vi.stubGlobal('fetch', fetchMock)
    await fetchDistrictRisk(
      'frost',
      { layer: 'frost-degree-hours', model: 'gfs', level: 0 },
      '2026101406',
      '2026101400',
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/hazards/district-risk?hazard=frost&model=gfs&level=0&time=2026101406&run=2026101400',
    )
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

describe('rasters served by TiTiler', () => {
  const forest = {
    id: 'forest', kind: 'raster' as const,
    tile_url: '/api/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?layer=forest',
  }

  it('uses the address the catalogue gives, adding the retry count', () => {
    expect(layerTileUrl(forest, null, 0)).toBe('/api/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?layer=forest')
    expect(layerTileUrl(forest, 2005, 2)).toBe('/api/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?layer=forest&r=2')
  })

  it('falls back to the portal tile route for a raster without its own address', () => {
    expect(layerTileUrl({ id: 'old', kind: 'raster' as const }, 2005, 0)).toBe('/api/tiles/old/{z}/{x}/{y}?year=2005')
    expect(layerTileUrl({ id: 'old', kind: 'raster' as const, tile_url: null }, null, 1)).toBe(
      '/api/tiles/old/{z}/{x}/{y}?r=1',
    )
  })

  it('probes the whole-world tile at that address', async () => {
    const ok = respond(200, null)
    vi.stubGlobal('fetch', ok)
    expect(await probeLayer(forest, null, 0)).toBe(true)
    expect(ok.mock.calls[0][0]).toBe('/api/cog/tiles/WebMercatorQuad/0/0/0.png?layer=forest')
  })
})
