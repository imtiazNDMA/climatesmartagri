import { useStore } from 'zustand'
import { createStore, type StoreApi } from 'zustand/vanilla'
import { COUNTRY_ID } from '../api/types'

export interface ActiveLayer {
  id: string
  opacity: number
  hidden: boolean
}

/** Everything that describes what is on screen. `layers[0]` draws on top. */
export interface View {
  section: string | null
  /** True when the open section's charts fill the map area. */
  full: boolean
  layers: ActiveLayer[]
  place: string | null
  year: number | null
}

export interface ViewActions {
  openSection(id: string): void
  closeSection(): void
  setFull(full: boolean): void
  toggleLayer(id: string, defaultOpacity: number): void
  removeLayer(id: string): void
  setOpacity(id: string, opacity: number): void
  toggleHidden(id: string): void
  moveLayer(id: string, toIndex: number): void
  selectPlace(id: string | null): void
  setYear(year: number | null): void
  replaceView(view: View): void
}

export type ViewStore = View & ViewActions

export const emptyView: View = { section: null, full: false, layers: [], place: null, year: null }

const tidyOpacity = (value: number) => Math.round(Math.min(1, Math.max(0, value)) * 100) / 100

export function createViewStore(initial: View = emptyView): StoreApi<ViewStore> {
  return createStore<ViewStore>()((set) => ({
    ...initial,
    openSection: (id) => set((s) => (s.section === id ? { section: null, full: false } : { section: id })),
    closeSection: () => set({ section: null, full: false }),
    setFull: (full) => set((s) => ({ full: full && s.section !== null })),
    toggleLayer: (id, defaultOpacity) =>
      set((s) =>
        s.layers.some((l) => l.id === id)
          ? { layers: s.layers.filter((l) => l.id !== id) }
          : { layers: [{ id, opacity: tidyOpacity(defaultOpacity), hidden: false }, ...s.layers] },
      ),
    removeLayer: (id) => set((s) => ({ layers: s.layers.filter((l) => l.id !== id) })),
    setOpacity: (id, opacity) =>
      set((s) =>
        Number.isNaN(opacity)
          ? s
          : { layers: s.layers.map((l) => (l.id === id ? { ...l, opacity: tidyOpacity(opacity) } : l)) },
      ),
    toggleHidden: (id) =>
      set((s) => ({ layers: s.layers.map((l) => (l.id === id ? { ...l, hidden: !l.hidden } : l)) })),
    moveLayer: (id, toIndex) =>
      set((s) => {
        const from = s.layers.findIndex((l) => l.id === id)
        if (from < 0) return s
        const next = [...s.layers]
        const [moved] = next.splice(from, 1)
        next.splice(Math.min(next.length, Math.max(0, toIndex)), 0, moved)
        return { layers: next }
      }),
    selectPlace: (id) => set({ place: id === COUNTRY_ID ? null : id }),
    setYear: (year) => set({ year }),
    replaceView: (view) => set({ ...view }),
  }))
}

export const viewStore = createViewStore()

export function useView<T>(selector: (state: ViewStore) => T): T {
  return useStore(viewStore, selector)
}

export function pickView(state: View): View {
  return { section: state.section, full: state.full, layers: state.layers, place: state.place, year: state.year }
}
