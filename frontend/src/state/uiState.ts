import { useStore } from 'zustand'
import { createStore, type StoreApi } from 'zustand/vanilla'

export interface Notice {
  id: number
  text: string
}

/** Transient interface state that does not belong in the URL. */
export interface UiStore {
  notices: Notice[]
  layerErrors: Record<string, boolean>
  retryCounts: Record<string, number>
  backendLost: boolean
  /** True while the forecast's tiles are on their way: the first request for a time waits on PMD. */
  forecastLoading: boolean
  addNotice(text: string): void
  dismissNotice(id: number): void
  setLayerError(id: string): void
  clearLayerError(id: string): void
  retryLayer(id: string): void
  forgetLayer(id: string): void
  setBackendLost(lost: boolean): void
  setForecastLoading(loading: boolean): void
}

function without<T>(record: Record<string, T>, key: string): Record<string, T> {
  const next = { ...record }
  delete next[key]
  return next
}

export function createUiStore(): StoreApi<UiStore> {
  let nextId = 1
  return createStore<UiStore>()((set) => ({
    notices: [],
    layerErrors: {},
    retryCounts: {},
    backendLost: false,
    forecastLoading: false,
    addNotice: (text) =>
      set((s) => (s.notices.some((n) => n.text === text) ? s : { notices: [...s.notices, { id: nextId++, text }] })),
    dismissNotice: (id) => set((s) => ({ notices: s.notices.filter((n) => n.id !== id) })),
    setLayerError: (id) => set((s) => (s.layerErrors[id] ? s : { layerErrors: { ...s.layerErrors, [id]: true } })),
    clearLayerError: (id) => set((s) => (s.layerErrors[id] ? { layerErrors: without(s.layerErrors, id) } : s)),
    retryLayer: (id) =>
      set((s) => ({
        layerErrors: without(s.layerErrors, id),
        retryCounts: { ...s.retryCounts, [id]: (s.retryCounts[id] ?? 0) + 1 },
      })),
    forgetLayer: (id) =>
      set((s) =>
        id in s.layerErrors || id in s.retryCounts
          ? { layerErrors: without(s.layerErrors, id), retryCounts: without(s.retryCounts, id) }
          : s,
      ),
    setBackendLost: (lost) => set((s) => (s.backendLost === lost ? s : { backendLost: lost })),
    setForecastLoading: (loading) => set((s) => (s.forecastLoading === loading ? s : { forecastLoading: loading })),
  }))
}

export const uiStore = createUiStore()

export function useUi<T>(selector: (state: UiStore) => T): T {
  return useStore(uiStore, selector)
}
