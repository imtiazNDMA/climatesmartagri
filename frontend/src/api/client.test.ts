import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  BackendUnreachableError,
  fetchBoundaries,
  fetchCatalogue,
  fetchSectionData,
  probeTile,
  tileUrlTemplate,
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
