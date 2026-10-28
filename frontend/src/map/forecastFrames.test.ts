import { beforeEach, describe, expect, it } from 'vitest'
import { ForecastFrames, type FrameMap } from './forecastFrames'

/** A map that remembers its layers and their opacity, and loads a source only when told to. */
class FakeMap implements FrameMap {
  layers = new Map<string, { opacity: number; before?: string; paint: Record<string, unknown>; visibility: string }>()
  sources = new Map<string, Record<string, unknown>>()
  loaded = new Set<string>()
  addSource(id: string, source: Record<string, unknown>) {
    this.sources.set(id, source)
  }
  addLayer(layer: Record<string, unknown>, before?: string) {
    const paint = layer.paint as Record<string, unknown>
    this.layers.set(layer.id as string, { opacity: paint['raster-opacity'] as number, before, paint, visibility: 'visible' })
  }
  removeLayer(id: string) {
    this.layers.delete(id)
  }
  removeSource(id: string) {
    this.sources.delete(id)
    this.loaded.delete(id)
  }
  getLayer(id: string) {
    return this.layers.get(id)
  }
  getSource(id: string) {
    return this.sources.get(id)
  }
  setPaintProperty(id: string, name: string, value: unknown) {
    const layer = this.layers.get(id)!
    if (name === 'raster-opacity') layer.opacity = value as number
    else layer.paint[name] = value
  }
  setLayoutProperty(id: string, _name: string, value: unknown) {
    this.layers.get(id)!.visibility = value as string
  }
  moveLayer(id: string, before?: string) {
    this.layers.get(id)!.before = before
  }
  isSourceLoaded(id: string) {
    return this.loaded.has(id)
  }
  opacities() {
    return Object.fromEntries([...this.layers].map(([id, layer]) => [id, layer.opacity]))
  }
}

let map: FakeMap
let frames: ForecastFrames
let loading: boolean[]
let timers: { run: () => void; ms: number }[]
const runTimers = () => timers.splice(0).forEach((timer) => timer.run())

beforeEach(() => {
  map = new FakeMap()
  loading = []
  timers = []
  frames = new ForecastFrames(map, {
    opacity: 0.75, fadeMs: 400, maxzoom: 7, bounds: [55, 18, 85, 42],
    anchor: () => 'borders',
    onLoading: (state) => loading.push(state),
    later: (run, ms) => timers.push({ run, ms }),
  })
})

describe('the first frame', () => {
  it('is added invisibly under the anchor, then fades in once its tiles have loaded', () => {
    frames.show('/a')
    expect(map.opacities()).toEqual({ 'forecast-1': 0 })
    expect(map.layers.get('forecast-1')!.before).toBe('borders')
    expect(map.sources.get('forecast-1')).toMatchObject({ tiles: ['/a'], maxzoom: 7, bounds: [55, 18, 85, 42] })
    expect(map.layers.get('forecast-1')!.paint['raster-opacity-transition']).toEqual({ duration: 400, delay: 0 })
    expect(loading).toEqual([true])

    frames.settle() // not loaded yet: nothing changes
    expect(map.opacities()).toEqual({ 'forecast-1': 0 })

    map.loaded.add('forecast-1')
    frames.settle()
    expect(map.opacities()).toEqual({ 'forecast-1': 0.75 })
    expect(loading).toEqual([true, false])
  })
})

describe('moving to another time', () => {
  beforeEach(() => {
    frames.show('/a')
    map.loaded.add('forecast-1')
    frames.settle()
  })

  it('keeps the old frame on screen until the new one has loaded, then blends between them', () => {
    frames.show('/b')
    expect(map.opacities()).toEqual({ 'forecast-1': 0.75, 'forecast-2': 0 })

    map.loaded.add('forecast-2')
    frames.settle()
    expect(map.opacities()).toEqual({ 'forecast-1': 0, 'forecast-2': 0.75 })
    expect(timers.map((timer) => timer.ms)).toEqual([450])

    runTimers() // the fade is over: the old frame leaves the map
    expect(map.opacities()).toEqual({ 'forecast-2': 0.75 })
    expect([...map.sources.keys()]).toEqual(['forecast-2'])
  })

  it('drops a frame still loading when a newer time is asked for', () => {
    frames.show('/b')
    frames.show('/c')
    expect(map.opacities()).toEqual({ 'forecast-1': 0.75, 'forecast-3': 0 })
    map.loaded.add('forecast-3')
    frames.settle()
    runTimers()
    expect(map.opacities()).toEqual({ 'forecast-3': 0.75 })
  })

  it('goes back to the frame on screen without reloading it', () => {
    frames.show('/b')
    frames.show('/a')
    expect(map.opacities()).toEqual({ 'forecast-1': 0.75 })
    expect(loading.at(-1)).toBe(false)
  })

  it('does nothing when asked for the frame already shown or already loading', () => {
    frames.show('/a')
    frames.show('/b')
    frames.show('/b')
    expect([...map.layers.keys()]).toEqual(['forecast-1', 'forecast-2'])
  })

  it('fades out and leaves when there is nothing to show', () => {
    frames.show(null)
    expect(map.opacities()).toEqual({ 'forecast-1': 0 })
    runTimers()
    expect(map.layers.size).toBe(0)
    expect(loading.at(-1)).toBe(false)
    frames.show(null)
    expect(timers).toEqual([])
  })

  it('puts its frames back under the anchor when asked', () => {
    frames.show('/b')
    map.layers.get('forecast-1')!.before = undefined
    map.layers.get('forecast-2')!.before = undefined
    frames.restack()
    expect([...map.layers.values()].map((layer) => layer.before)).toEqual(['borders', 'borders'])
  })
})

describe('a frame loaded in advance', () => {
  beforeEach(() => {
    frames.show('/a')
    map.loaded.add('forecast-1')
    frames.settle()
    loading.length = 0
  })

  it('waits out of sight without counting as loading', () => {
    frames.preload('/b')
    expect(map.opacities()).toEqual({ 'forecast-1': 0.75, 'forecast-2': 0 })
    expect(loading).toEqual([])
    map.loaded.add('forecast-2')
    frames.settle() // loaded, but nobody has asked for it: it stays hidden
    expect(map.opacities()).toEqual({ 'forecast-1': 0.75, 'forecast-2': 0 })
  })

  it('blends in at once when asked for, if its tiles are already there', () => {
    frames.preload('/b')
    map.loaded.add('forecast-2')
    frames.show('/b')
    expect(map.opacities()).toEqual({ 'forecast-1': 0, 'forecast-2': 0.75 })
    expect([...map.layers.keys()]).toEqual(['forecast-1', 'forecast-2']) // reused, not added again
    expect(loading).toEqual([true, false])
  })

  it('blends in when its last tiles arrive, if asked for before then', () => {
    frames.preload('/b')
    frames.show('/b')
    expect(map.opacities()).toEqual({ 'forecast-1': 0.75, 'forecast-2': 0 })
    map.loaded.add('forecast-2')
    frames.settle()
    expect(map.opacities()).toEqual({ 'forecast-1': 0, 'forecast-2': 0.75 })
  })

  it('is dropped when another is preloaded, when a different frame is shown, and with the forecast', () => {
    frames.preload('/b')
    frames.preload('/c')
    expect([...map.layers.keys()]).toEqual(['forecast-1', 'forecast-3'])
    frames.preload('/c')
    expect([...map.layers.keys()]).toEqual(['forecast-1', 'forecast-3'])
    frames.preload('/a') // already on screen: nothing to load
    expect([...map.layers.keys()]).toEqual(['forecast-1'])
    frames.preload('/d')
    frames.show(null)
    runTimers()
    expect(map.layers.size).toBe(0)
  })

  it('is not counted as shown, so its failures are not reported as the current time failing', () => {
    frames.preload('/b')
    expect(frames.shows('forecast-1')).toBe(true)
    expect(frames.shows('forecast-2')).toBe(false)
    frames.show('/b')
    expect(frames.shows('forecast-2')).toBe(true)
    expect(frames.shows(undefined)).toBe(false)
  })

  it('is kept under the anchor with the others', () => {
    frames.preload('/b')
    map.layers.get('forecast-2')!.before = undefined
    frames.restack()
    expect(map.layers.get('forecast-2')!.before).toBe('borders')
  })
})

describe('owning sources', () => {
  it('recognises its own sources by name', () => {
    expect(ForecastFrames.owns('forecast-4')).toBe(true)
    expect(ForecastFrames.owns('data-forest')).toBe(false)
    expect(ForecastFrames.owns(undefined)).toBe(false)
  })
})

describe('frames of an annual layer', () => {
  let annual: ForecastFrames
  beforeEach(() => {
    annual = new ForecastFrames(map, {
      opacity: 0.85, fadeMs: 400, maxzoom: 14, prefix: 'data-trees@', attribution: 'Esri',
      anchor: () => 'borders', onLoading: (state) => loading.push(state), later: (run, ms) => timers.push({ run, ms }),
    })
  })

  it('names its sources after the layer, and owns only those', () => {
    annual.show('https://tiles/2019/{z}/{x}/{y}')
    expect([...map.sources.keys()]).toEqual(['data-trees@1'])
    expect(map.sources.get('data-trees@1')).toMatchObject({ attribution: 'Esri', maxzoom: 14 })
    expect(annual.ownsSource('data-trees@1')).toBe(true)
    expect(annual.ownsSource('forecast-1')).toBe(false)
  })

  it('changes the opacity of the frame on screen at once, and blends later frames to it', () => {
    annual.show('a')
    map.loaded.add('data-trees@1')
    annual.settle()
    annual.setOpacity(0.4)
    const front = map.layers.get('data-trees@1')!
    expect(front.opacity).toBe(0.4)
    expect(front.paint['raster-opacity-transition']).toEqual({ duration: 400, delay: 0 })
    annual.show('b')
    map.loaded.add('data-trees@2')
    annual.settle()
    expect(map.opacities()['data-trees@2']).toBe(0.4)
  })

  it('hides its frames, including one that arrives while hidden', () => {
    annual.show('a')
    map.loaded.add('data-trees@1')
    annual.settle()
    annual.setVisible(false)
    expect(map.layers.get('data-trees@1')!.visibility).toBe('none')
    annual.show('b')
    map.loaded.add('data-trees@2')
    annual.settle()
    expect(map.layers.get('data-trees@2')!.visibility).toBe('none')
    annual.setVisible(true)
    expect(map.layers.get('data-trees@2')!.visibility).toBe('visible')
  })

  it('takes every frame off the map at once when disposed, and stops counting as loading', () => {
    annual.show('a')
    map.loaded.add('data-trees@1')
    annual.settle()
    annual.show('b')
    annual.preload('c')
    loading.length = 0
    annual.dispose()
    expect(map.layers.size).toBe(0)
    expect(map.sources.size).toBe(0)
    expect(loading).toEqual([false])
  })
})
