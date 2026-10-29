/**
 * A raster layer on the map as a sequence of frames, one per time: the forecast's hours, or an annual
 * layer's years. A new frame is added invisibly, loads its tiles, and only then fades in while the one
 * before fades out, so stepping through times blends one picture into the next and the map is never
 * left blank between them.
 */

/** The part of the map the frames need. MapLibre's map fits it. */
export interface FrameMap {
  addSource(id: string, source: Record<string, unknown>): unknown
  addLayer(layer: Record<string, unknown>, beforeId?: string): unknown
  removeLayer(id: string): unknown
  removeSource(id: string): unknown
  getLayer(id: string): unknown
  getSource(id: string): unknown
  setPaintProperty(layerId: string, name: string, value: unknown): unknown
  setLayoutProperty(layerId: string, name: string, value: unknown): unknown
  moveLayer(id: string, beforeId?: string): unknown
  isSourceLoaded(id: string): boolean
}

export interface FrameOptions {
  /** How opaque a frame is once it has faded in. */
  opacity: number
  /** How long one frame takes to blend into the next, in milliseconds. Zero swaps at once. */
  fadeMs: number
  /** West, south, east, north: no tiles are asked for outside it. */
  bounds?: [number, number, number, number]
  maxzoom: number
  /** Credit for the imagery, shown by the map. */
  attribution?: string
  /** What every frame's source and layer id starts with. */
  prefix?: string
  /** The layer frames are placed under. */
  anchor(): string | undefined
  /** Told when a frame starts loading and when the map has caught up. */
  onLoading(loading: boolean): void
  /** Runs something later; the browser's timer unless a test supplies its own. */
  later?(run: () => void, ms: number): void
}

interface Frame {
  id: string
  tiles: string
}

export const FRAME_PREFIX = 'forecast-'

export class ForecastFrames {
  private front: Frame | null = null
  private pending: Frame | null = null
  /** A frame loaded out of sight because it is likely to be asked for next. */
  private ahead: Frame | null = null
  private count = 0
  private visible = true
  private readonly map: FrameMap
  private readonly options: FrameOptions
  private readonly prefix: string

  constructor(map: FrameMap, options: FrameOptions) {
    this.map = map
    this.options = { ...options }
    this.prefix = options.prefix ?? FRAME_PREFIX
  }

  /** True for a source that belongs to a forecast frame. */
  static owns(sourceId: string | undefined): boolean {
    return sourceId !== undefined && sourceId.startsWith(FRAME_PREFIX)
  }

  /** True for a source that belongs to one of these frames. */
  ownsSource(sourceId: string | undefined): boolean {
    return sourceId !== undefined && sourceId.startsWith(this.prefix)
  }

  /** How opaque the frame on screen is; changed at once, not blended. */
  setOpacity(opacity: number): void {
    if (opacity === this.options.opacity) return
    this.options.opacity = opacity
    const front = this.front
    if (!front || !this.map.getLayer(front.id)) return
    this.map.setPaintProperty(front.id, 'raster-opacity-transition', { duration: 0, delay: 0 })
    this.map.setPaintProperty(front.id, 'raster-opacity', opacity)
    this.map.setPaintProperty(front.id, 'raster-opacity-transition', { duration: this.options.fadeMs, delay: 0 })
  }

  /** Hide or show the frames. A hidden layer loads no tiles, so one loaded in advance stays visible, at nothing. */
  setVisible(visible: boolean): void {
    if (visible === this.visible) return
    this.visible = visible
    for (const frame of [this.front, this.pending]) {
      if (frame && this.map.getLayer(frame.id)) this.map.setLayoutProperty(frame.id, 'visibility', visible ? 'visible' : 'none')
    }
  }

  /** Take every frame off the map at once. */
  dispose(): void {
    for (const frame of [this.front, this.pending, this.ahead]) if (frame) this.remove(frame.id)
    if (this.pending) this.options.onLoading(false)
    this.front = this.pending = this.ahead = null
  }

  /** True for the source of the frame on screen or on its way there, not one only loaded in advance. */
  shows(sourceId: string | undefined): boolean {
    return sourceId !== undefined && (sourceId === this.front?.id || sourceId === this.pending?.id)
  }

  /** Show the frame at this tile address, or nothing for null. */
  show(tiles: string | null): void {
    if (tiles === (this.pending ?? this.front)?.tiles || (tiles === null && !this.pending && !this.front)) return
    // Whatever was on its way is no longer wanted.
    if (this.pending) {
      this.remove(this.pending.id)
      this.pending = null
    }
    if (tiles === null) {
      if (this.front) this.retire(this.front)
      this.front = null
      this.preload(null)
      this.options.onLoading(false)
      return
    }
    if (tiles === this.front?.tiles) {
      this.options.onLoading(false)
      return
    }
    if (tiles === this.ahead?.tiles) {
      // Loaded in advance: it can start blending in at once, or as soon as its last tiles arrive.
      this.pending = this.ahead
      this.ahead = null
      this.options.onLoading(true)
      this.settle()
      return
    }
    this.pending = this.add(tiles)
    this.options.onLoading(true)
  }

  /**
   * Load a frame out of sight, ready for when it is asked for. One is kept at a time: preloading another,
   * or null, drops the one before.
   */
  preload(tiles: string | null): void {
    if (tiles === this.ahead?.tiles) return
    if (this.ahead) this.remove(this.ahead.id)
    this.ahead = tiles === null || tiles === this.front?.tiles || tiles === this.pending?.tiles ? null : this.add(tiles)
  }

  /** Put a frame on the map with nothing of it showing yet. */
  private add(tiles: string): Frame {
    const id = `${this.prefix}${++this.count}`
    this.map.addSource(id, {
      type: 'raster', tiles: [tiles], tileSize: 256, maxzoom: this.options.maxzoom, bounds: this.options.bounds,
      ...(this.options.attribution ? { attribution: this.options.attribution } : {}),
    })
    this.map.addLayer(
      {
        id, type: 'raster', source: id,
        layout: { visibility: 'visible' },
        paint: {
          'raster-opacity': 0,
          'raster-opacity-transition': { duration: this.options.fadeMs, delay: 0 },
          // The blend between frames is this class's doing; a second fade per tile would fight it.
          'raster-fade-duration': 0,
        },
      },
      this.options.anchor(),
    )
    return { id, tiles }
  }

  /** Call when the map reports progress loading a source, or has gone idle. */
  settle(): void {
    const next = this.pending
    if (!next || !this.map.getSource(next.id) || !this.map.isSourceLoaded(next.id)) return
    if (!this.visible) this.map.setLayoutProperty(next.id, 'visibility', 'none')
    this.map.setPaintProperty(next.id, 'raster-opacity', this.options.opacity)
    if (this.front) this.retire(this.front)
    this.front = next
    this.pending = null
    this.options.onLoading(false)
  }

  /** Put the frames back under the anchor, after other layers have been added or moved. */
  restack(): void {
    for (const frame of [this.front, this.pending, this.ahead]) {
      if (frame && this.map.getLayer(frame.id)) this.map.moveLayer(frame.id, this.options.anchor())
    }
  }

  /** Fade a frame out, then take it off the map. */
  private retire(frame: Frame): void {
    if (this.map.getLayer(frame.id)) this.map.setPaintProperty(frame.id, 'raster-opacity', 0)
    const later = this.options.later ?? ((run, ms) => void window.setTimeout(run, ms))
    later(() => this.remove(frame.id), this.options.fadeMs + 50)
  }

  private remove(id: string): void {
    if (this.map.getLayer(id)) this.map.removeLayer(id)
    if (this.map.getSource(id)) this.map.removeSource(id)
  }
}
