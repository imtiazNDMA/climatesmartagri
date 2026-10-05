import { Map as MapLibreMap, NavigationControl, Popup, setWorkerUrl, type StyleSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { useEffect, useRef, useState } from 'react'
import { tileUrlTemplate } from '../api/client'
import { COUNTRY_ID, type Layer } from '../api/types'
import type { PortalData } from '../data/usePortalData'
import { clickTarget, effectiveYear } from '../state/selectors'
import { uiStore, useUi } from '../state/uiState'
import { useView, viewStore } from '../state/viewState'

// MapLibre looks for its worker beside its own module, which a bundler moves; point it at the bundled copy.
setWorkerUrl(workerUrl)

const BLANK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#eef1f4' } }],
}

const dataId = (layerId: string) => `data-${layerId}`

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
        'fill-color': '#1d4ed8',
        'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 0.15, 0],
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
  const popup = new Popup({ closeButton: false, closeOnClick: false })
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
    popup.setLngLat(event.lngLat).setText(String(feature.properties.name)).addTo(map)
  })
  map.on('mouseleave', 'districts-fill', () => {
    clearHover()
    map.getCanvas().style.cursor = ''
    popup.remove()
  })
  map.on('click', 'districts-fill', (event) => {
    const feature = event.features?.[0]
    if (!feature) return
    const target = clickTarget(data.places, viewStore.getState().place, String(feature.properties.id))
    if (target) viewStore.getState().selectPlace(target)
  })
}

function addDataLayer(map: MapLibreMap, layer: Layer, year: number | null, retry: number) {
  const id = dataId(layer.id)
  const tiles = [`${window.location.origin}${tileUrlTemplate(layer.id, year, retry)}`]
  if (layer.kind === 'vector') {
    const colour = layer.legend?.type === 'classes' ? layer.legend.items[0].colour : '#1d4ed8'
    map.addSource(id, { type: 'vector', tiles })
    map.addLayer({ id, type: 'fill', source: id, 'source-layer': layer.id, paint: { 'fill-color': colour } })
  } else {
    map.addSource(id, { type: 'raster', tiles, tileSize: 256 })
    map.addLayer({ id, type: 'raster', source: id })
  }
}

function removeDataLayer(map: MapLibreMap, layerId: string) {
  const id = dataId(layerId)
  if (map.getLayer(id)) map.removeLayer(id)
  if (map.getSource(id)) map.removeSource(id)
}

/** Data layers sit under every boundary layer, so borders stay readable. */
function boundaryAnchor(map: MapLibreMap): string | undefined {
  return ['districts-fill', 'provinces-line'].find((id) => map.getLayer(id))
}

export function MapView({ data }: { data: PortalData }) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const built = useRef(new Map<string, string>())
  const [ready, setReady] = useState(false)
  const [boundariesDrawn, setBoundariesDrawn] = useState(false)
  const layers = useView((s) => s.layers)
  const place = useView((s) => s.place)
  const year = useView((s) => s.year)
  const retryCounts = useUi((s) => s.retryCounts)

  useEffect(() => {
    let cancelled = false
    let map: MapLibreMap | null = null
    const builtLayers = built.current
    const country = data.places.find((p) => p.id === COUNTRY_ID)

    resolveStyle(data.catalogue.basemap_style_url).then(({ style, fallback }) => {
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
        addBoundaries(created, data)
        wireInteractions(created, data)
        mapRef.current = created
        setReady(true)
      })
      created.on('sourcedata', (event) => {
        if (!cancelled && event.sourceId === 'districts' && event.isSourceLoaded) setBoundariesDrawn(true)
      })
      // Best effort: flag a layer whose tiles start failing after its first check passed.
      created.on('error', (event) => {
        const sourceId = (event as { sourceId?: string }).sourceId
        if (sourceId?.startsWith('data-')) uiStore.getState().setLayerError(sourceId.slice(5))
      })
    })

    return () => {
      cancelled = true
      map?.remove()
      mapRef.current = null
      builtLayers.clear()
      setReady(false)
      setBoundariesDrawn(false)
    }
  }, [data])

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
    if (target) map.fitBounds(target.bbox, { padding: 48, duration: 600 })
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
      map.setPaintProperty(id, layer.kind === 'vector' ? 'fill-opacity' : 'raster-opacity', active.opacity)
    }
  }, [ready, layers, year, retryCounts, data])

  return <div ref={container} className="map" data-map-ready={ready} data-boundaries-drawn={boundariesDrawn} />
}
