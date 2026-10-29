import type { StyleSpecification } from 'maplibre-gl'

export type BasemapId = 'positron' | 'liberty' | 'bright' | 'streets' | 'satellite'

export interface Basemap {
  id: BasemapId
  label: string
  description: string
  style: string | StyleSpecification
  imagery?: boolean
}

const rasterStyle = (
  id: string,
  tiles: string[],
  attribution: string,
  maxzoom: number,
): StyleSpecification => ({
  version: 8,
  sources: { [id]: { type: 'raster', tiles, tileSize: 256, maxzoom, attribution } },
  layers: [
    { id: `${id}-background`, type: 'background', paint: { 'background-color': '#e8edf2' } },
    { id, type: 'raster', source: id },
  ],
})

export const BASEMAPS: Basemap[] = [
  {
    id: 'positron',
    label: 'Positron',
    description: 'Clean, low-contrast reference map',
    style: 'https://tiles.openfreemap.org/styles/positron',
  },
  {
    id: 'liberty',
    label: 'Liberty',
    description: 'Detailed general-purpose map',
    style: 'https://tiles.openfreemap.org/styles/liberty',
  },
  {
    id: 'bright',
    label: 'Bright',
    description: 'High-contrast streets and labels',
    style: 'https://tiles.openfreemap.org/styles/bright',
  },
  {
    id: 'streets',
    label: 'OpenStreetMap',
    description: 'Standard community street map',
    style: rasterStyle(
      'osm',
      ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      '© OpenStreetMap contributors',
      19,
    ),
  },
  {
    id: 'satellite',
    label: 'Satellite',
    description: 'World imagery for field context',
    imagery: true,
    style: rasterStyle(
      'esri-imagery',
      ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
      'Tiles © Esri',
      19,
    ),
  },
]

export function basemapById(id: BasemapId): Basemap {
  return BASEMAPS.find((basemap) => basemap.id === id) ?? BASEMAPS[0]
}
