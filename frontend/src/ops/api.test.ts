import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { opsApi } from './api'

function respond(status: number, body: unknown) {
  return vi.fn(async (_url: string, _init?: RequestInit) => new Response(JSON.stringify(body), { status }))
}

afterEach(() => vi.unstubAllGlobals())

describe('ops api', () => {
  it('sends the token with every request and unwraps lists', async () => {
    const fetchMock = respond(200, { runs: [{ id: 'r1' }] })
    vi.stubGlobal('fetch', fetchMock)

    expect(await opsApi('tok').runs()).toEqual([{ id: 'r1' }])
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/ops/eval-runs')
    expect(new Headers(init?.headers).get('X-Ops-Token')).toBe('tok')
  })

  it('builds trace filters without empty values and encodes ids', async () => {
    const fetchMock = respond(200, { traces: [], next: null })
    vi.stubGlobal('fetch', fetchMock)

    await opsApi('tok').traces({ source: 'live', status: undefined, before: '2026|a b' })
    await opsApi('tok').compare('a/1', 'b')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/ops/traces?source=live&before=2026%7Ca+b')
    expect(fetchMock.mock.calls[1][0]).toBe('/api/ops/eval-runs/compare?a=a%2F1&b=b')
  })

  it('posts labels as JSON', async () => {
    const fetchMock = respond(201, { id: 'l1' })
    vi.stubGlobal('fetch', fetchMock)

    await opsApi('tok').label({ result_id: 'r', labeller: 'officer', faithful: true, helpful: 4, note: '' })
    const init = fetchMock.mock.calls[0][1]!
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(JSON.parse(init.body as string)).toEqual({ result_id: 'r', labeller: 'officer', faithful: true, helpful: 4, note: '' })
  })

  it('turns a refused token into an ApiError with its reason', async () => {
    vi.stubGlobal('fetch', respond(401, { detail: { reason: 'ops-unauthorized', message: 'A valid X-Ops-Token header is required' } }))

    const error = await opsApi('bad').metrics('24h').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).reason).toBe('ops-unauthorized')
    expect((error as ApiError).status).toBe(401)
  })
})
