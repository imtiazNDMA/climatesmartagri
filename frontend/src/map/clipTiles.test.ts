import { describe, expect, it, vi } from 'vitest'
import {
  clipTemplate,
  makeClipLoader,
  outlineFrom,
  parseClipUrl,
  tileBbox,
  toTilePixels,
  type Outline,
} from './clipTiles'

const square: Outline = outlineFrom({
  type: 'Feature',
  properties: {},
  geometry: { type: 'Polygon', coordinates: [[[60, 20], [80, 20], [80, 30], [60, 30], [60, 20]]] },
})

describe('clip addresses', () => {
  it('wrap a tile template so the tile position reaches the clipper', () => {
    const template = clipTemplate('https://mpc.test/tiles/{z}/{x}/{y}@1x.png?colormap=%7B%7D')
    expect(template).toBe('clip://{z}/{x}/{y}/https://mpc.test/tiles/{z}/{x}/{y}@1x.png?colormap=%7B%7D')

    const filled = template.replaceAll('{z}', '6').replaceAll('{x}', '42').replaceAll('{y}', '26')
    expect(parseClipUrl(filled)).toEqual({
      z: 6, x: 42, y: 26, upstream: 'https://mpc.test/tiles/6/42/26@1x.png?colormap=%7B%7D',
    })
  })

  it('refuse anything that is not a clip address', () => {
    expect(parseClipUrl('https://mpc.test/6/42/26.png')).toBeNull()
    expect(parseClipUrl('clip://6/42/https://mpc.test/x.png')).toBeNull()
  })
})

describe('tile geometry', () => {
  it('places longitude and latitude on the tile in Web Mercator pixels', () => {
    expect(toTilePixels([[0, 0]], 0, 0, 0, 256)).toEqual([[128, 128]])
    const [[left, top]] = toTilePixels([[-180, 85.0511287798]], 0, 0, 0, 256)
    expect(left).toBeCloseTo(0, 6)
    expect(top).toBeCloseTo(0, 3)
    // The same point lands 256 pixels further on in the next tile's frame of reference.
    expect(toTilePixels([[0, 0]], 1, 0, 0, 256)).toEqual([[256, 256]])
  })

  it('gives a tile its extent in degrees', () => {
    const [west, south, east, north] = tileBbox(1, 1, 0)
    expect([west, east]).toEqual([0, 180])
    expect(south).toBeCloseTo(0, 6)
    expect(north).toBeCloseTo(85.0511287798, 6)
  })

  it('reads every ring of a polygon or multipolygon outline and its extent', () => {
    const multi = outlineFrom({
      type: 'Feature',
      properties: {},
      geometry: {
        type: 'MultiPolygon',
        coordinates: [
          [[[60, 20], [61, 20], [61, 21], [60, 20]]],
          [[[70, 25], [72, 25], [72, 27], [70, 25]], [[71, 25.5], [71.5, 25.5], [71.5, 26], [71, 25.5]]],
        ],
      },
    })
    expect(multi.rings).toHaveLength(3)
    expect(multi.bbox).toEqual([60, 20, 72, 27])
  })
})

/** Stand-ins for the browser's image work, recording what the loader asks of them. */
function fakes(outline: Outline | null, upstream: { status: number } = { status: 200 }) {
  const image = { width: 256 } as ImageBitmap
  const blank = { width: 1 } as ImageBitmap
  const drawn = { width: 256, drawn: true } as unknown as ImageBitmap
  return {
    image, blank, drawn,
    deps: {
      outline: vi.fn(async () => outline),
      fetchImage: vi.fn(async () => {
        if (upstream.status !== 200) return { status: upstream.status } as const
        return { status: 200, image } as const
      }),
      draw: vi.fn(async () => drawn),
      blank: vi.fn(async () => blank),
    },
  }
}

const request = (z: number, x: number, y: number) => ({
  url: `clip://${z}/${x}/${y}/https://mpc.test/${z}/${x}/${y}.png`,
})

describe('the clip loader', () => {
  it('draws a tile over the country inside the outline only', async () => {
    const { deps, drawn, image } = fakes(square)
    const result = await makeClipLoader(deps)(request(6, 44, 26), new AbortController())

    expect(result.data).toBe(drawn)
    expect(deps.fetchImage).toHaveBeenCalledWith('https://mpc.test/6/44/26.png', expect.any(AbortSignal))
    const [drawnImage, rings] = deps.draw.mock.calls[0] as unknown as [ImageBitmap, number[][][]]
    expect(drawnImage).toBe(image)
    expect(rings).toHaveLength(1)
    expect(rings[0][0]).toEqual(toTilePixels([[60, 20]], 6, 44, 26, 256)[0])
  })

  it('asks nothing of the tile server for a tile wholly outside the country', async () => {
    const { deps, blank } = fakes(square)
    const result = await makeClipLoader(deps)(request(6, 10, 10), new AbortController())

    expect(result.data).toBe(blank)
    expect(deps.fetchImage).not.toHaveBeenCalled()
  })

  it('draws nothing where the tile server has no data, without raising an error', async () => {
    const { deps, blank } = fakes(square, { status: 404 })
    const result = await makeClipLoader(deps)(request(6, 44, 26), new AbortController())
    expect(result.data).toBe(blank)
  })

  it('fails a tile the tile server cannot serve, so the layer can say so', async () => {
    const { deps } = fakes(square, { status: 503 })
    await expect(makeClipLoader(deps)(request(6, 44, 26), new AbortController())).rejects.toThrow('503')
  })

  it('draws the whole tile when the outline cannot be had, rather than nothing', async () => {
    const { deps, image } = fakes(null)
    const result = await makeClipLoader(deps)(request(6, 10, 10), new AbortController())

    expect(deps.fetchImage).toHaveBeenCalled()
    expect(result.data).toBe(image)
    expect(deps.draw).not.toHaveBeenCalled()
  })
})
