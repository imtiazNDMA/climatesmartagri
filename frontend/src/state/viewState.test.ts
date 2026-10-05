import { beforeEach, describe, expect, it } from 'vitest'
import { createViewStore, pickView } from './viewState'

let store: ReturnType<typeof createViewStore>
const ids = () => store.getState().layers.map((l) => l.id)

beforeEach(() => {
  store = createViewStore()
})

describe('sections', () => {
  it('opens, switches and toggles closed', () => {
    store.getState().openSection('a')
    expect(store.getState().section).toBe('a')
    store.getState().openSection('b')
    expect(store.getState().section).toBe('b')
    store.getState().openSection('b')
    expect(store.getState().section).toBeNull()
  })

  it('keeps layers when the section changes or closes', () => {
    store.getState().openSection('a')
    store.getState().toggleLayer('x', 1)
    store.getState().openSection('b')
    store.getState().closeSection()
    expect(ids()).toEqual(['x'])
  })
})

describe('layers', () => {
  it('adds new layers on top with their default opacity', () => {
    store.getState().toggleLayer('x', 0.8)
    store.getState().toggleLayer('y', 1)
    expect(store.getState().layers).toEqual([
      { id: 'y', opacity: 1, hidden: false },
      { id: 'x', opacity: 0.8, hidden: false },
    ])
  })

  it('toggling an active layer removes it', () => {
    store.getState().toggleLayer('x', 1)
    store.getState().toggleLayer('x', 1)
    expect(ids()).toEqual([])
  })

  it('removes, hides and sets opacity', () => {
    store.getState().toggleLayer('x', 1)
    store.getState().toggleLayer('y', 1)
    store.getState().toggleHidden('x')
    store.getState().setOpacity('y', 0.35)
    expect(store.getState().layers).toEqual([
      { id: 'y', opacity: 0.35, hidden: false },
      { id: 'x', opacity: 1, hidden: true },
    ])
    store.getState().removeLayer('y')
    expect(ids()).toEqual(['x'])
  })

  it('clamps and rounds opacity, and ignores NaN', () => {
    store.getState().toggleLayer('x', 5)
    expect(store.getState().layers[0].opacity).toBe(1)
    store.getState().setOpacity('x', -3)
    expect(store.getState().layers[0].opacity).toBe(0)
    store.getState().setOpacity('x', 0.8500000001)
    expect(store.getState().layers[0].opacity).toBe(0.85)
    store.getState().setOpacity('x', Number.NaN)
    expect(store.getState().layers[0].opacity).toBe(0.85)
  })

  it('reorders, clamping the target index', () => {
    for (const id of ['c', 'b', 'a']) store.getState().toggleLayer(id, 1)
    expect(ids()).toEqual(['a', 'b', 'c'])
    store.getState().moveLayer('c', 0)
    expect(ids()).toEqual(['c', 'a', 'b'])
    store.getState().moveLayer('c', 99)
    expect(ids()).toEqual(['a', 'b', 'c'])
    store.getState().moveLayer('b', -4)
    expect(ids()).toEqual(['b', 'a', 'c'])
    store.getState().moveLayer('ghost', 0)
    expect(ids()).toEqual(['b', 'a', 'c'])
  })

  it('ignores actions on layers that are not active', () => {
    store.getState().setOpacity('ghost', 0.5)
    store.getState().toggleHidden('ghost')
    store.getState().removeLayer('ghost')
    expect(ids()).toEqual([])
  })
})

describe('place and year', () => {
  it('selects a province then a district, then steps back', () => {
    store.getState().selectPlace('PK1')
    store.getState().selectPlace('PK101')
    expect(store.getState().place).toBe('PK101')
    store.getState().selectPlace('PK1')
    expect(store.getState().place).toBe('PK1')
    store.getState().selectPlace(null)
    expect(store.getState().place).toBeNull()
  })

  it('treats the country id as no selection', () => {
    store.getState().selectPlace('PK')
    expect(store.getState().place).toBeNull()
  })

  it('sets and clears the year', () => {
    store.getState().setYear(2005)
    expect(store.getState().year).toBe(2005)
    store.getState().setYear(null)
    expect(store.getState().year).toBeNull()
  })
})

describe('replaceView and pickView', () => {
  it('round-trips a whole view', () => {
    const view = {
      section: 'a',
      full: true,
      layers: [{ id: 'x', opacity: 0.5, hidden: true }],
      place: 'PK1',
      year: 2001,
    }
    store.getState().replaceView(view)
    expect(pickView(store.getState())).toEqual(view)
  })
})

describe('full view', () => {
  it('opens and closes', () => {
    store.getState().openSection('a')
    store.getState().setFull(true)
    expect(store.getState().full).toBe(true)
    store.getState().setFull(false)
    expect(store.getState().full).toBe(false)
  })

  it('stays open when switching to another section', () => {
    store.getState().openSection('a')
    store.getState().setFull(true)
    store.getState().openSection('b')
    expect(store.getState().full).toBe(true)
  })

  it('ends when the section is closed, either way', () => {
    store.getState().openSection('a')
    store.getState().setFull(true)
    store.getState().openSection('a')
    expect(store.getState().full).toBe(false)
    store.getState().openSection('a')
    store.getState().setFull(true)
    store.getState().closeSection()
    expect(store.getState().full).toBe(false)
  })

  it('cannot be opened without a section', () => {
    store.getState().setFull(true)
    expect(store.getState().full).toBe(false)
  })
})
