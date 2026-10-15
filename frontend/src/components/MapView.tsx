import { Map as MapLibreMap, NavigationControl, Popup, setWorkerUrl, type StyleSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { useEffect, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { createRoot } from 'react-dom/client'
import { forecastTileUrl, layerGeojsonUrl, layerTileUrl } from '../api/client'
import { COUNTRY_ID, type Layer } from '../api/types'
import type { ForecastTimesState } from '../data/useForecastTimes'
import type { DistrictRiskState } from '../data/useDistrictRisk'
import type { PortalData } from '../data/usePortalData'
import type { StoryCamera } from '../api/types'
import { runOf } from '../forecast/choice'
import { ForecastFrames, type FrameMap } from '../map/forecastFrames'
import { basemapById, type BasemapId } from '../map/basemaps'
import { extremeColours, fillColour, glowStrength, shapeColour } from '../map/layerStyle'
import { tooltipTable } from '../map/tooltip'
import { DEFAULT_RISK_COLOURS, districtRiskColour, districtRiskOpacity } from '../map/districtRisk'
import { clickTarget, effectiveYear } from '../state/selectors'
import { uiStore, useUi } from '../state/uiState'
import { useView, viewStore } from '../state/viewState'
import { MapPopup, type PopupBlock } from './MapPopup'

// MapLibre looks for its worker beside its own module, which a bundler moves; point it at the bundled copy.
setWorkerUrl(workerUrl)

const BLANK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#eef1f4' } }],
}

const DARK_MAP_BACKGROUND = '#0b1320'

function applyMapTheme(map: MapLibreMap, darkMode: boolean, imagery = false) {
  const boundaryPaint: Record<string, { colour: string; opacity: number }> = {
    'districts-line': {
      colour: darkMode ? '#8aa0ba' : '#64748b',
      opacity: darkMode ? 0.78 : 1,
    },
    'provinces-line': {
      colour: darkMode ? '#d2dfef' : '#334155',
      opacity: darkMode ? 0.92 : 1,
    },
    'selected-province': {
      colour: darkMode ? '#f8fafc' : '#0f172a',
      opacity: 1,
    },
    'selected-district': {
      colour: darkMode ? '#60a5fa' : '#1d4ed8',
      opacity: 1,
    },
  }
  for (const layer of map.getStyle().layers ?? []) {
    if (layer.id.startsWith('data-') || layer.id.startsWith('forecast')) continue
    if (boundaryPaint[layer.id]) {
      const paint = boundaryPaint[layer.id]
      map.setPaintProperty(layer.id, 'line-color', paint.colour)
      map.setPaintProperty(layer.id, 'line-opacity', paint.opacity)
      continue
    }
    if (layer.id === 'districts-fill') {
      continue
    }

    if (layer.type === 'background') {
      map.setPaintProperty(layer.id, 'background-color', darkMode ? DARK_MAP_BACKGROUND : '#eef1f4')
    } else if (layer.type === 'raster') {
      map.setPaintProperty(layer.id, 'raster-brightness-max', darkMode ? (imagery ? 0.72 : 0.42) : 1)
      map.setPaintProperty(layer.id, 'raster-brightness-min', darkMode ? (imagery ? 0.03 : 0.08) : 0)
      map.setPaintProperty(layer.id, 'raster-contrast', darkMode ? (imagery ? 0.08 : 0.18) : 0)
      map.setPaintProperty(layer.id, 'raster-saturation', darkMode ? (imagery ? -0.18 : -0.72) : 0)
      map.setPaintProperty(layer.id, 'raster-hue-rotate', darkMode && !imagery ? 20 : 0)
    } else if (layer.type === 'fill') {
      map.setPaintProperty(layer.id, 'fill-color', darkMode ? '#172235' : '#f1f3f2')
    } else if (layer.type === 'line') {
      map.setPaintProperty(layer.id, 'line-color', darkMode ? '#3d4f68' : '#c4c9ca')
    } else if (layer.type === 'symbol') {
      if (layer.paint?.['text-color'] !== undefined) {
        map.setPaintProperty(layer.id, 'text-color', darkMode ? '#b9c6d8' : '#374151')
      }
      if (layer.paint?.['text-halo-color'] !== undefined) {
        map.setPaintProperty(layer.id, 'text-halo-color', darkMode ? '#0b1320' : '#ffffff')
      }
    }
  }
}

const dataId = (layerId: string) => `data-${layerId}`
/** The weather forecast: rasters drawn over the data layers and under the boundaries, one per time. */
const FORECAST_ID = 'forecast'
const FORECAST_OPACITY = 0.75
/** How long one forecast time takes to blend into the next. */
const FORECAST_FADE_MS = 450
/**
 * What is drawn on the shapes a layer marks as extreme: a pale wash and a fill in the shape's own colour,
 * which take turns so the shape dims and brightens, then a soft halo and a crisp edge round it.
 */
const washId = (layerId: string) => `${dataId(layerId)}-wash`
const pulseId = (layerId: string) => `${dataId(layerId)}-pulse`
const glowId = (layerId: string) => `${dataId(layerId)}-glow`
const edgeId = (layerId: string) => `${dataId(layerId)}-edge`

/** Use the online background map if it answers, otherwise a plain background. */
async function resolveStyle(url: string): Promise<{ style: string | StyleSpecification; fallback: boolean }> {
  try {
    const response = await fetch(url)
    if (!response.ok) throw new Error(String(response.status))
    return { style: url, fallback: false }
  } catch {
    return { style: BLANK_STYLE, fallback: true }
  }
}

function addBoundaries(map: MapLibreMap, data: PortalData) {
  const { province, district } = data.boundaries
  if (district) {
    map.addSource('districts', { type: 'geojson', data: district, promoteId: 'id' })
    map.addLayer({
      id: 'districts-fill',
      type: 'fill',
      source: 'districts',
      paint: {
        'fill-color': districtRiskColour(DEFAULT_RISK_COLOURS, '#1d4ed8') as never,
        'fill-opacity': districtRiskOpacity as never,
      },
    })
    map.addLayer({
      id: 'districts-line', type: 'line', source: 'districts',
      paint: { 'line-color': '#64748b', 'line-width': 0.5 },
    })
  }
  if (province) {
    map.addSource('provinces', { type: 'geojson', data: province, promoteId: 'id' })
    map.addLayer({
      id: 'provinces-line', type: 'line', source: 'provinces',
      paint: { 'line-color': '#334155', 'line-width': 1.5 },
    })
    map.addLayer({
      id: 'selected-province', type: 'line', source: 'provinces',
      filter: ['==', ['get', 'id'], ''],
      paint: { 'line-color': '#0f172a', 'line-width': 2.5 },
    })
  }
  if (district) {
    map.addLayer({
      id: 'selected-district', type: 'line', source: 'districts',
      filter: ['==', ['get', 'id'], ''],
      paint: { 'line-color': '#1d4ed8', 'line-width': 3 },
    })
  }
}

function wireInteractions(map: MapLibreMap, data: PortalData) {
  if (!map.getLayer('districts-fill')) return
  let hovered: string | null = null
  // Opened by a click and left open until it is closed or another spot is clicked.
  const popup = new Popup({ closeButton: true, closeOnClick: false, maxWidth: '700px', className: 'map-popup' })
  const card = document.createElement('div')
  const cardRoot = createRoot(card)
  const clearHover = () => {
    if (hovered) map.setFeatureState({ source: 'districts', id: hovered }, { hover: false })
    hovered = null
  }

  map.on('mousemove', 'districts-fill', (event) => {
    const feature = event.features?.[0]
    if (!feature) return
    const id = String(feature.properties.id)
    if (hovered !== id) {
      clearHover()
      hovered = id
      map.setFeatureState({ source: 'districts', id }, { hover: true })
    }
    map.getCanvas().style.cursor = 'pointer'
  })
  map.on('mouseleave', 'districts-fill', () => {
    clearHover()
    map.getCanvas().style.cursor = ''
  })
  // A click on the map that lands outside every district clears the selection and closes the popup.
  map.on('click', (event) => {
    if (map.queryRenderedFeatures(event.point, { layers: ['districts-fill'] }).length > 0) return
    popup.remove()
    if (viewStore.getState().place !== null) viewStore.getState().selectPlace(null)
  })
  map.on('click', 'districts-fill', (event) => {
    const feature = event.features?.[0]
    if (!feature) return
    // The district and its province, then what each visible shape layer says about this spot.
    const district = data.places.find((p) => p.id === String(feature.properties.id))
    const province = data.places.find((p) => p.id === district?.parent_id)
    const blocks: PopupBlock[] = []
    for (const under of map.queryRenderedFeatures(event.point)) {
      const label = under.properties?.label
      const layer = data.catalogue.layers.find((l) => dataId(l.id) === under.layer.id)
      if (!layer || typeof label !== 'string' || blocks.some((b) => b.layerId === layer.id)) continue
      blocks.push({
        layerId: layer.id,
        layerTitle: layer.title,
        colour: shapeColour(layer, under.properties),
        label,
        // A shape that carries a table shows it in place of its one-line label.
        table: tooltipTable(under.properties),
      })
    }
    // Drawn at once, so the popup is placed by the size of what it actually holds.
    flushSync(() =>
      cardRoot.render(
        <MapPopup place={String(feature.properties.name)} parent={province?.name ?? null} blocks={blocks} />,
      ),
    )
    popup.setLngLat(event.lngLat).setDOMContent(card).addTo(map)
    const target = clickTarget(data.places, viewStore.getState().place, String(feature.properties.id))
    if (target) viewStore.getState().selectPlace(target)
  })
}

/** How solid the shape's own colour is at the bright end of a blink, and how much it is paled at the dim end. */
const PULSE_FILL = 1
const PULSE_WASH = 0.6

function addDataLayer(map: MapLibreMap, layer: Layer, year: number | null, retry: number) {
  const id = dataId(layer.id)
  if (layer.kind === 'geojson') {
    map.addSource(id, { type: 'geojson', data: `${window.location.origin}${layerGeojsonUrl(layer.id, retry)}` })
    map.addLayer({
      id,
      type: 'fill',
      source: id,
      // The expression is built from the catalogue's legend, so it is typed loosely here.
      paint: { 'fill-color': fillColour(layer) as never, 'fill-outline-color': 'rgba(255, 255, 255, 0.7)' },
    })
    // Shapes the data marks as extreme blink as a whole, each in its own shade: paled by a wash, then
    // filled solid. Their outline glows in the colour of their end of the ramp.
    const ends = extremeColours(layer)
    if (ends) {
      const colour = ['match', ['get', 'extreme'], 'low', ends.low, ends.high] as never
      const marked = ['has', 'extreme'] as never
      map.addLayer({
        id: washId(layer.id), type: 'fill', source: id, filter: marked,
        paint: { 'fill-color': '#ffffff', 'fill-opacity': 0 },
      })
      map.addLayer({
        id: pulseId(layer.id), type: 'fill', source: id, filter: marked,
        paint: { 'fill-color': fillColour(layer) as never, 'fill-opacity': PULSE_FILL },
      })
      map.addLayer({
        id: glowId(layer.id), type: 'line', source: id, filter: marked,
        layout: { 'line-join': 'round' },
        paint: { 'line-color': colour, 'line-width': 16, 'line-blur': 12, 'line-opacity': 1 },
      })
      map.addLayer({
        id: edgeId(layer.id), type: 'line', source: id, filter: marked,
        layout: { 'line-join': 'round' },
        paint: { 'line-color': colour, 'line-width': 3, 'line-opacity': 1 },
      })
    }
    return
  }
  const tiles = [`${window.location.origin}${layerTileUrl(layer, year, retry)}`]
  if (layer.kind === 'vector') {
    const colour = layer.legend?.type === 'classes' ? layer.legend.items[0].colour : '#1d4ed8'
    map.addSource(id, { type: 'vector', tiles })
    map.addLayer({ id, type: 'fill', source: id, 'source-layer': layer.id, paint: { 'fill-color': colour } })
  } else {
    // Beyond the data's own detail the map stretches tiles and asks for no more, and outside the
    // data's extent it asks for none at all (the tile server answers those with 404).
    map.addSource(id, {
      type: 'raster', tiles, tileSize: 256, maxzoom: layer.max_zoom ?? 22, bounds: layer.bounds ?? undefined,
    })
    map.addLayer({ id, type: 'raster', source: id })
  }
}

function removeDataLayer(map: MapLibreMap, layerId: string) {
  const id = dataId(layerId)
  for (const part of [glowId(layerId), edgeId(layerId), pulseId(layerId), washId(layerId), id]) {
    if (map.getLayer(part)) map.removeLayer(part)
  }
  if (map.getSource(id)) map.removeSource(id)
}

/** Data layers sit under every boundary layer, so borders stay readable. */
function boundaryAnchor(map: MapLibreMap): string | undefined {
  return ['districts-fill', 'provinces-line'].find((id) => map.getLayer(id))
}

export function MapView({
  data,
  darkMode,
  basemap,
  forecastTimes,
  districtRisk,
  storyCamera,
}: {
  data: PortalData
  darkMode: boolean
  basemap: BasemapId
  forecastTimes: ForecastTimesState
  districtRisk: DistrictRiskState
  storyCamera: StoryCamera | null
}) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const built = useRef(new Map<string, string>())
  const framesRef = useRef<ForecastFrames | null>(null)
  const shownForecast = useRef<string | null>(null)
  const frameChoice = useRef<string | null>(null)
  const riskDistricts = useRef(new Set<string>())
  const [ready, setReady] = useState(false)
  const [boundariesDrawn, setBoundariesDrawn] = useState(false)
  // The place the camera last came to rest on, or '' while it is moving. Tests wait on it before clicking.
  const [cameraOn, setCameraOn] = useState('')
  const layers = useView((s) => s.layers)
  const place = useView((s) => s.place)
  const year = useView((s) => s.year)
  const retryCounts = useUi((s) => s.retryCounts)
  const forecast = useView((s) => s.forecast)
  const forecastRun =
    forecastTimes.status === 'ready' ? runOf(forecastTimes.times, forecast?.time ?? null) : null

  useEffect(() => {
    let cancelled = false
    let map: MapLibreMap | null = null
    const builtLayers = built.current
    const riskSet = riskDistricts.current
    const country = data.places.find((p) => p.id === COUNTRY_ID)

    const selectedBasemap = basemapById(basemap)
    const requestedStyle = basemap === 'positron' && data.catalogue.basemap_style_url
      ? data.catalogue.basemap_style_url
      : selectedBasemap.style
    const stylePromise = typeof requestedStyle === 'string'
      ? resolveStyle(requestedStyle)
      : Promise.resolve({ style: requestedStyle, fallback: false })
    stylePromise.then(({ style, fallback }) => {
      if (cancelled || !container.current) return
      if (fallback) {
        uiStore.getState().addNotice('Background map unavailable. Data is shown on a plain background.')
      }
      let created: MapLibreMap
      try {
        created = new MapLibreMap({
          container: container.current,
          style,
          bounds: country?.bbox,
          fitBoundsOptions: { padding: 24 },
        })
      } catch {
        uiStore.getState().addNotice('The map could not start in this browser.')
        return
      }
      map = created
      created.addControl(new NavigationControl({ showCompass: false }), 'bottom-right')
      created.on('load', () => {
        if (cancelled) return
        applyMapTheme(created, darkMode, selectedBasemap.imagery)
        addBoundaries(created, data)
        wireInteractions(created, data)
        mapRef.current = created
        setReady(true)
      })
      // A frame whose tiles were all in hand already reports no further progress; idle catches it.
      created.on('idle', () => {
        if (!cancelled) framesRef.current?.settle()
      })
      created.on('sourcedata', (event) => {
        if (!cancelled && event.sourceId === 'districts' && event.isSourceLoaded) setBoundariesDrawn(true)
        if (!cancelled && ForecastFrames.owns(event.sourceId)) framesRef.current?.settle()
      })
      // Best effort: flag a layer whose tiles start failing after its first check passed.
      created.on('error', (event) => {
        const sourceId = (event as { sourceId?: string }).sourceId
        if (sourceId?.startsWith('data-')) uiStore.getState().setLayerError(sourceId.slice(5))
        if (framesRef.current?.shows(sourceId)) {
          uiStore.getState().setLayerError(FORECAST_ID)
          uiStore.getState().setForecastLoading(false)
        }
      })
    })

    return () => {
      cancelled = true
      map?.remove()
      mapRef.current = null
      builtLayers.clear()
      framesRef.current = null
      shownForecast.current = null
      frameChoice.current = null
      riskSet.clear()
      setReady(false)
      setBoundariesDrawn(false)
    }
    // Built from places, boundaries and the background style only: a refreshed layer list must not rebuild the map.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.places, data.boundaries, data.catalogue.basemap_style_url, basemap])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    applyMapTheme(map, darkMode, basemapById(basemap).imagery)
  }, [darkMode, ready, basemap])

  // Story mode moves the map as the guide advances through its narrative chapters.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || !storyCamera) return
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reducedMotion) {
      map.jumpTo(storyCamera)
      return
    }
    map.flyTo({ ...storyCamera, essential: false })
  }, [ready, storyCamera])

  // Shade districts by the selected hazard's low, medium, and high guidance thresholds.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || !map.getSource('districts')) return
    if (districtRisk.status === 'loading' && !districtRisk.clear) return
    for (const id of riskDistricts.current) {
      map.removeFeatureState({ source: 'districts', id }, 'risk')
    }
    riskDistricts.current.clear()
    const colours = districtRisk.status === 'ready' ? districtRisk.data.colours : DEFAULT_RISK_COLOURS
    map.setPaintProperty(
      'districts-fill',
      'fill-color',
      districtRiskColour(colours, darkMode ? '#60a5fa' : '#1d4ed8') as never,
    )
    if (districtRisk.status !== 'ready') return
    for (const district of districtRisk.data.districts) {
      if (!district.risk) continue
      map.setFeatureState({ source: 'districts', id: district.id }, { risk: district.risk })
      riskDistricts.current.add(district.id)
    }
  }, [ready, districtRisk, darkMode])

  // Outline the selection and move the map to it.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const selected = data.places.find((p) => p.id === place)
    const provinceId = selected?.level === 'district' ? selected.parent_id ?? '' : selected?.id ?? ''
    const districtId = selected?.level === 'district' ? selected.id : ''
    if (map.getLayer('selected-province')) map.setFilter('selected-province', ['==', ['get', 'id'], provinceId])
    if (map.getLayer('selected-district')) map.setFilter('selected-district', ['==', ['get', 'id'], districtId])
    const target = selected ?? data.places.find((p) => p.id === COUNTRY_ID)
    if (target) {
      setCameraOn('')
      // An interrupted move also ends, so each move names its own place and the last one to end wins.
      map.once('moveend', () => setCameraOn(target.id))
      map.fitBounds(target.bbox, { padding: 48, duration: 600 })
    }
  }, [ready, place, data])

  // Keep the map's data layers in step with the active layers list.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const wanted = new Map<string, string>()
    for (const active of layers) {
      const layer = data.catalogue.layers.find((l) => l.id === active.id)
      if (layer) wanted.set(layer.id, `${effectiveYear(layer.years, year) ?? ''}|${retryCounts[layer.id] ?? 0}`)
    }
    for (const [id, key] of [...built.current]) {
      if (wanted.get(id) !== key) {
        removeDataLayer(map, id)
        built.current.delete(id)
      }
    }
    const anchor = boundaryAnchor(map)
    // Bottom of the list first: each layer is placed just under the boundaries,
    // so later (higher) layers end up above earlier ones.
    for (const active of [...layers].reverse()) {
      const layer = data.catalogue.layers.find((l) => l.id === active.id)
      if (!layer) continue
      if (!built.current.has(layer.id)) {
        addDataLayer(map, layer, effectiveYear(layer.years, year), retryCounts[layer.id] ?? 0)
        built.current.set(layer.id, wanted.get(layer.id)!)
      }
      const id = dataId(layer.id)
      map.moveLayer(id, anchor)
      map.setLayoutProperty(id, 'visibility', active.hidden ? 'none' : 'visible')
      map.setPaintProperty(id, layer.kind === 'raster' ? 'raster-opacity' : 'fill-opacity', active.opacity)
      // The glow stays with its layer: just above it, and hidden when it is.
      for (const part of [washId(layer.id), pulseId(layer.id), glowId(layer.id), edgeId(layer.id)]) {
        if (!map.getLayer(part)) continue
        map.moveLayer(part, anchor)
        map.setLayoutProperty(part, 'visibility', active.hidden ? 'none' : 'visible')
      }
    }
  }, [ready, layers, year, retryCounts, data])

  // Keep the forecast in step with the chosen layer, model, level and time, blending from one time to the next.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    if (!framesRef.current) {
      framesRef.current = new ForecastFrames(map as unknown as FrameMap, {
        opacity: FORECAST_OPACITY,
        fadeMs: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : FORECAST_FADE_MS,
        // The models' grids are coarse; beyond zoom 7 the map stretches tiles and asks for no more.
        maxzoom: 7,
        bounds: data.catalogue.forecast?.bbox,
        anchor: () => boundaryAnchor(map),
        onLoading: (loading) => uiStore.getState().setForecastLoading(loading),
      })
    }
    // A time is drawn once the run it comes from is known; until then whatever is on screen stays.
    const tiles =
      forecast?.time && forecastRun
        ? `${window.location.origin}${forecastTileUrl(forecast, forecast.time, forecastRun)}`
        : null
    const choiceKey = forecast ? `${forecast.layer}|${forecast.model}|${forecast.level}` : null
    const sameChoice = choiceKey === frameChoice.current
    frameChoice.current = choiceKey
    if (forecast?.time && !forecastRun) {
      // Still waiting to learn the run. Another time of the same layer stays up meanwhile; a frame of some
      // other layer, model or level does not, since the key and panel no longer describe it.
      if (!sameChoice) {
        shownForecast.current = null
        framesRef.current.show(null)
      }
      return
    }
    if (tiles !== shownForecast.current) {
      uiStore.getState().clearLayerError(FORECAST_ID)
      shownForecast.current = tiles
    }
    framesRef.current.show(tiles)
    // Load the time after this one out of sight, so stepping or playing on to it starts blending at once.
    const offered = forecastTimes.status === 'ready' ? forecastTimes.times : []
    const next = forecast?.time ? offered[(offered.findIndex((t) => t.time === forecast.time) + 1) % (offered.length || 1)] : undefined
    framesRef.current.preload(
      forecast && tiles && next && next.time !== forecast.time
        ? `${window.location.origin}${forecastTileUrl(forecast, next.time, next.run)}`
        : null,
    )
    // Placed after the data layers each time they change, so it stays above them.
    framesRef.current.restack()
  }, [ready, forecast, forecastRun, forecastTimes, layers, year, retryCounts, data])

  // Extreme shapes blink, fill and outline together, unless the reader has asked for less motion.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const glowing = layers.filter((active) => !active.hidden && map.getLayer(glowId(active.id)))
    if (glowing.length === 0) return
    const timer = window.setInterval(() => {
      const strength = glowStrength(performance.now())
      for (const active of glowing) {
        if (!map.getLayer(glowId(active.id))) continue
        map.setPaintProperty(washId(active.id), 'fill-opacity', PULSE_WASH * (1 - strength))
        map.setPaintProperty(pulseId(active.id), 'fill-opacity', PULSE_FILL * strength)
        map.setPaintProperty(glowId(active.id), 'line-opacity', strength)
        map.setPaintProperty(edgeId(active.id), 'line-opacity', 0.35 + 0.65 * strength)
      }
    }, 50)
    return () => window.clearInterval(timer)
  }, [ready, layers, data])

  return <div ref={container} className="map" data-map-ready={ready} data-boundaries-drawn={boundariesDrawn} data-camera-on={cameraOn} />
}
