import { useStore } from 'zustand'
import { createStore, type StoreApi } from 'zustand/vanilla'
import { COUNTRY_ID, type PortalAction } from '../api/types'
import type { ForecastChoice } from '../forecast/choice'

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
  /** The weather forecast on the map, if one is. */
  forecast: ForecastChoice | null
}

/** What is on screen but not worth keeping in a link. */
export interface Passing {
  /** The one chart that fills the full view, by id, or null when every chart is shown. */
  maximized: string | null
}

export interface ViewActions {
  openSection(id: string): void
  closeSection(): void
  setFull(full: boolean): void
  /** Opens the full view on one chart alone; null brings the others back. */
  maximize(chartId: string | null): void
  toggleLayer(id: string, defaultOpacity: number): void
  removeLayer(id: string): void
  setOpacity(id: string, opacity: number): void
  toggleHidden(id: string): void
  moveLayer(id: string, toIndex: number): void
  selectPlace(id: string | null): void
  setYear(year: number | null): void
  setForecast(choice: ForecastChoice | null): void
  /** Moves the forecast on the map to another time; does nothing when there is none. */
  setForecastTime(time: string | null): void
  replaceView(view: View): void
}

export type ViewStore = View & Passing & ViewActions

export const emptyView: View = {
  section: null, full: false, layers: [], place: null, year: null, forecast: null,
}

const tidyOpacity = (value: number) => Math.round(Math.min(1, Math.max(0, value)) * 100) / 100

export function createViewStore(initial: View = emptyView): StoreApi<ViewStore> {
  return createStore<ViewStore>()((set) => ({
    ...initial,
    maximized: null,
    openSection: (id) =>
      set((s) => (s.section === id ? { section: null, full: false, maximized: null } : { section: id, maximized: null })),
    closeSection: () => set({ section: null, full: false, maximized: null }),
    setFull: (full) => set((s) => ({ full: full && s.section !== null, maximized: null })),
    maximize: (chartId) =>
      set((s) => (s.section === null ? s : chartId === null ? { maximized: null } : { full: true, maximized: chartId })),
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
    setForecast: (forecast) => set({ forecast }),
    setForecastTime: (time) =>
      set((s) => (s.forecast && s.forecast.time !== time ? { forecast: { ...s.forecast, time } } : s)),
    replaceView: (view) => set({ ...view }),
  }))
}

export const viewStore = createViewStore()

export function useView<T>(selector: (state: ViewStore) => T): T {
  return useStore(viewStore, selector)
}

export function pickView(state: View): View {
  return {
    section: state.section, full: state.full, layers: state.layers, place: state.place, year: state.year,
    forecast: state.forecast,
  }
}

/**
 * Apply the view changes the assistant requested. Only recognised action types are
 * applied; open-section is guarded so it cannot toggle a section closed, and
 * toggle-layer is ensure-on so it never hides a layer that is already visible.
 */
export function applyPortalActions(actions: PortalAction[], store: StoreApi<ViewStore> = viewStore): void {
  for (const action of actions) {
    const state = store.getState()
    switch (action.type) {
      case 'open-section':
        if (state.section !== action.section_id) state.openSection(action.section_id)
        break
      case 'select-place':
        state.selectPlace(action.place_id)
        break
      case 'set-year':
        state.setYear(action.year)
        break
      case 'toggle-layer': {
        const existing = state.layers.find((layer) => layer.id === action.layer_id)
        if (!existing) state.toggleLayer(action.layer_id, action.default_opacity)
        else if (existing.hidden) state.toggleHidden(action.layer_id)
        break
      }
      case 'set-forecast':
        state.setForecast({ ...action.forecast })
        break
    }
  }
}
