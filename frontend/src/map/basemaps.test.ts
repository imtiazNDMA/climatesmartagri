import { describe, expect, it } from 'vitest'
import { BASEMAPS, basemapById } from './basemaps'

describe('basemaps', () => {
  it('provides unique selectable maps', () => {
    expect(new Set(BASEMAPS.map((item) => item.id)).size).toBe(BASEMAPS.length)
    expect(BASEMAPS.map((item) => item.id)).toEqual(['positron', 'liberty', 'bright', 'streets', 'satellite'])
  })

  it('falls back to Positron for an unknown persisted value', () => {
    expect(basemapById('unknown' as never).id).toBe('positron')
  })

  it('includes attribution on raster maps', () => {
    for (const basemap of BASEMAPS.filter((item) => typeof item.style !== 'string')) {
      const style = basemap.style as { sources: Record<string, { attribution?: string }> }
      const sources = Object.values(style.sources)
      expect(sources.every((source) => Boolean(source.attribution))).toBe(true)
    }
  })
})
