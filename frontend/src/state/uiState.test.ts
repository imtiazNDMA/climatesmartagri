import { beforeEach, describe, expect, it } from 'vitest'
import { createUiStore } from './uiState'

let store: ReturnType<typeof createUiStore>

beforeEach(() => {
  store = createUiStore()
})

describe('notices', () => {
  it('adds, de-duplicates and dismisses', () => {
    store.getState().addNotice('one')
    store.getState().addNotice('one')
    store.getState().addNotice('two')
    expect(store.getState().notices.map((n) => n.text)).toEqual(['one', 'two'])
    store.getState().dismissNotice(store.getState().notices[0].id)
    expect(store.getState().notices.map((n) => n.text)).toEqual(['two'])
  })
})

describe('layer errors', () => {
  it('marks and clears an error', () => {
    store.getState().setLayerError('x')
    expect(store.getState().layerErrors).toEqual({ x: true })
    store.getState().clearLayerError('x')
    expect(store.getState().layerErrors).toEqual({})
  })

  it('retry clears the error and bumps the count', () => {
    store.getState().setLayerError('x')
    store.getState().retryLayer('x')
    store.getState().retryLayer('x')
    expect(store.getState().layerErrors).toEqual({})
    expect(store.getState().retryCounts).toEqual({ x: 2 })
  })

  it('forgetLayer drops both, and is a no-op for unknown layers', () => {
    store.getState().setLayerError('x')
    store.getState().retryLayer('x')
    const before = store.getState().retryCounts
    store.getState().forgetLayer('ghost')
    expect(store.getState().retryCounts).toBe(before)
    store.getState().forgetLayer('x')
    expect(store.getState().retryCounts).toEqual({})
    expect(store.getState().layerErrors).toEqual({})
  })
})

describe('backend lost', () => {
  it('sets and clears', () => {
    store.getState().setBackendLost(true)
    expect(store.getState().backendLost).toBe(true)
    store.getState().setBackendLost(false)
    expect(store.getState().backendLost).toBe(false)
  })
})

describe('forecast loading', () => {
  it('sets and clears', () => {
    expect(store.getState().forecastLoading).toBe(false)
    store.getState().setForecastLoading(true)
    expect(store.getState().forecastLoading).toBe(true)
    store.getState().setForecastLoading(false)
    expect(store.getState().forecastLoading).toBe(false)
  })
})
