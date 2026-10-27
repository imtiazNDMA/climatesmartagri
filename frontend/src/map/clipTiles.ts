/**
 * Planetary Computer tiles cut to Pakistan's outline. Its tiles cover whole item footprints, which
 * spill into India, Afghanistan and Iran, so each tile is fetched here, everything outside the
 * country is cut away on a canvas, and MapLibre is handed what is left. The tiles still come
 * straight from Planetary Computer to the browser; only the outline comes from the portal.
 */
import { addProtocol } from 'maplibre-gl'

export const CLIP_PROTOCOL = 'clip'
const TILE_SIZE = 256
const OUTLINE_URL = '/api/land-cover/outline'

type Ring = number[][]

/** The country's rings in degrees, and its extent as west, south, east, north. */
export interface Outline {
  rings: Ring[]
  bbox: [number, number, number, number]
}

interface OutlineFeature {
  geometry: { type: 'Polygon'; coordinates: Ring[] } | { type: 'MultiPolygon'; coordinates: Ring[][] }
  [key: string]: unknown
}

/** A tile template whose tiles are cut to the outline. The tile position travels in front of it. */
export const clipTemplate = (template: string) => `${CLIP_PROTOCOL}://{z}/{x}/{y}/${template}`

const CLIP_URL = /^clip:\/\/(\d+)\/(\d+)\/(\d+)\/(.+)$/

export function parseClipUrl(url: string): { z: number; x: number; y: number; upstream: string } | null {
  const match = CLIP_URL.exec(url)
  if (!match || !/^https?:\/\//.test(match[4])) return null
  return { z: Number(match[1]), x: Number(match[2]), y: Number(match[3]), upstream: match[4] }
}

export function outlineFrom(feature: OutlineFeature): Outline {
  const { geometry } = feature
  const rings = geometry.type === 'Polygon' ? geometry.coordinates : geometry.coordinates.flat()
  const bbox: Outline['bbox'] = [Infinity, Infinity, -Infinity, -Infinity]
  for (const ring of rings) {
    for (const [lon, lat] of ring) {
      bbox[0] = Math.min(bbox[0], lon)
      bbox[1] = Math.min(bbox[1], lat)
      bbox[2] = Math.max(bbox[2], lon)
      bbox[3] = Math.max(bbox[3], lat)
    }
  }
  return { rings, bbox }
}

const latitudeOf = (y: number, z: number) => (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / 2 ** z))) * 180) / Math.PI

/** A tile's extent in degrees: west, south, east, north. */
export function tileBbox(z: number, x: number, y: number): [number, number, number, number] {
  const n = 2 ** z
  return [(x / n) * 360 - 180, latitudeOf(y + 1, z), ((x + 1) / n) * 360 - 180, latitudeOf(y, z)]
}

/** Longitude and latitude as Web Mercator pixels on tile z/x/y. */
export function toTilePixels(ring: Ring, z: number, x: number, y: number, size: number): Ring {
  const n = 2 ** z
  return ring.map(([lon, lat]) => {
    const phi = (lat * Math.PI) / 180
    const across = (((lon + 180) / 360) * n - x) * size
    const down = (((1 - Math.log(Math.tan(phi) + 1 / Math.cos(phi)) / Math.PI) / 2) * n - y) * size
    return [across, down]
  })
}

const overlaps = (a: Outline['bbox'], b: Outline['bbox']) =>
  a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3]

type Fetched = { status: 200; image: ImageBitmap } | { status: number; image?: undefined }

export interface ClipDeps {
  /** The country's outline, or null when it cannot be had. */
  outline(): Promise<Outline | null>
  fetchImage(url: string, signal: AbortSignal): Promise<Fetched>
  /** The image with everything outside the pixel rings cut away. */
  draw(image: ImageBitmap, rings: Ring[]): Promise<ImageBitmap>
  blank(): Promise<ImageBitmap>
}

export function makeClipLoader(deps: ClipDeps) {
  return async (params: { url: string }, abortController: AbortController): Promise<{ data: ImageBitmap }> => {
    const tile = parseClipUrl(params.url)
    if (!tile) throw new Error(`Not a clip address: ${params.url}`)
    const { z, x, y, upstream } = tile
    const outline = await deps.outline()
    if (outline && !overlaps(tileBbox(z, x, y), outline.bbox)) return { data: await deps.blank() }

    const fetched = await deps.fetchImage(upstream, abortController.signal)
    // Outside the classification's items there is simply no data, which is not a failure.
    if (fetched.status === 404) return { data: await deps.blank() }
    if (!fetched.image) throw new Error(`Tile ${z}/${x}/${y} failed with ${fetched.status}`)
    // Without the outline the whole tile is better than none.
    if (!outline) return { data: fetched.image }
    const rings = outline.rings.map((ring) => toTilePixels(ring, z, x, y, TILE_SIZE))
    return { data: await deps.draw(fetched.image, rings) }
  }
}

let outlineRequest: Promise<Outline | null> | null = null

/** The outline is asked for once; a failure leaves the tiles unclipped rather than missing. */
function loadOutline(): Promise<Outline | null> {
  outlineRequest ??= fetch(OUTLINE_URL)
    .then(async (response) => (response.ok ? outlineFrom((await response.json()) as OutlineFeature) : null))
    .catch(() => null)
  return outlineRequest
}

const browserDeps: ClipDeps = {
  outline: loadOutline,
  async fetchImage(url, signal) {
    const response = await fetch(url, { signal })
    if (!response.ok) return { status: response.status }
    return { status: 200, image: await createImageBitmap(await response.blob()) }
  },
  async draw(image, rings) {
    const canvas = new OffscreenCanvas(TILE_SIZE, TILE_SIZE)
    const context = canvas.getContext('2d')!
    context.beginPath()
    for (const ring of rings) {
      ring.forEach(([px, py], i) => (i === 0 ? context.moveTo(px, py) : context.lineTo(px, py)))
      context.closePath()
    }
    context.clip('evenodd')
    context.drawImage(image, 0, 0, TILE_SIZE, TILE_SIZE)
    image.close()
    return canvas.transferToImageBitmap()
  },
  async blank() {
    // A canvas without a context cannot hand over a bitmap, so it is given one it never draws with.
    const canvas = new OffscreenCanvas(TILE_SIZE, TILE_SIZE)
    canvas.getContext('2d')
    return canvas.transferToImageBitmap()
  },
}

let registered = false

/** Teaches MapLibre the clip:// addresses. Safe to call more than once. */
export function registerClipProtocol() {
  if (registered) return
  registered = true
  addProtocol(CLIP_PROTOCOL, makeClipLoader(browserDeps))
}
