import { useEffect } from 'react'
import { AlertTriangle, CloudFog, CloudRain, Snowflake, ThermometerSun, Wind, type LucideIcon } from 'lucide-react'
import type { ForecastCatalogue, HazardProduct } from '../api/types'
import type { ForecastTimesState } from '../data/useForecastTimes'
import type { HazardProductsState } from '../data/useHazardProducts'
import type { DistrictRiskState } from '../data/useDistrictRisk'
import { chooseLayer, formatRun, formatTime, levelsFor } from '../forecast/choice'
import { useView, viewStore } from '../state/viewState'

const ICONS: Record<string, LucideIcon> = {
  frost: Snowflake,
  'heat-stress': ThermometerSun,
  'heavy-rain': CloudRain,
  'strong-wind': Wind,
  'low-visibility': CloudFog,
}

const threshold = (product: HazardProduct, value: number) =>
  `${product.direction === 'above' ? '≥' : '≤'} ${value} ${product.unit}`

const riskLabel = (index: number, count: number) =>
  index === count - 1 ? 'High risk' : index === 0 ? 'Low risk' : 'Medium risk'

export function HazardsPanel({
  catalogue,
  products,
  times,
  districtRisk,
}: {
  catalogue: ForecastCatalogue | null
  products: HazardProductsState
  times: ForecastTimesState
  districtRisk: DistrictRiskState
}) {
  const choice = useView((state) => state.forecast)

  // Open on the first product that has data, so the map is not blank when the section first opens.
  useEffect(() => {
    if (!catalogue || products.status !== 'ready' || choice !== null) return
    for (const product of products.data.products) {
      const next = chooseLayer(catalogue, product.forecast_layer, null)
      if (next) {
        viewStore.getState().setForecast(next)
        return
      }
    }
  }, [catalogue, products, choice])

  if (!catalogue) return <p className="empty">Forecast data is not loaded.</p>
  if (products.status === 'loading') return <p className="empty">Loading hazard guidance…</p>
  if (products.status === 'error') return <p className="deck-warning" role="alert">Hazard guidance could not load: {products.message}</p>

  const active = products.data.products.find((product) => product.forecast_layer === choice?.layer) ?? null
  const choose = (product: HazardProduct) => {
    const next = chooseLayer(catalogue, product.forecast_layer, choice)
    if (next) viewStore.getState().setForecast(next)
  }
  const layer = catalogue.layers.find((item) => item.id === choice?.layer)
  const availableModels = layer
    ? catalogue.models.filter((model) => levelsFor(layer, model.id).length > 0)
    : []
  const slot = times.status === 'ready' ? times.times.find((item) => item.time === choice?.time) : undefined

  return (
    <div className="hazards-panel">
      <section className="hazard-guidance-banner">
        <AlertTriangle size={20} aria-hidden />
        <div><strong>Forecast guidance</strong><p>{products.data.disclaimer}</p></div>
      </section>

      <div className="hazard-product-grid" role="group" aria-label="Hazard products">
        {products.data.products.map((product) => {
          const Icon = ICONS[product.id] ?? AlertTriangle
          const on = active?.id === product.id
          const available = catalogue.layers.some((item) => item.id === product.forecast_layer && Object.values(item.levels).some((levels) => levels.length))
          return (
            <button
              key={product.id}
              type="button"
              className={on ? 'on' : ''}
              aria-pressed={on}
              disabled={!available}
              onClick={() => choose(product)}
            >
              <span><Icon size={20} aria-hidden /></span>
              <strong>{product.title}</strong>
              <small>{available ? product.summary : 'No current PMD layer available'}</small>
            </button>
          )
        })}
      </div>

      {active && layer && choice && (
        <section className="hazard-detail">
          <header><div><span>On the map</span><h3>{active.title}</h3></div>{slot && <time>{formatTime(slot.time)}</time>}</header>
          <p>{active.summary}</p>
          {slot && <small>PMD model run: {formatRun(slot.run)}</small>}
          <div className="hazard-bands">
            {active.bands.map((band, index) => (
              <div key={band.severity}>
                <i style={{ background: band.colour }} />
                <span>
                  <strong>{riskLabel(index, active.bands.length)} · {band.label}</strong>
                  <small>{threshold(active, band.threshold)}</small>
                </span>
              </div>
            ))}
          </div>
          <label className="hazard-model">
            <span>Forecast model</span>
            <select value={choice.model} onChange={(event) => {
              const model = event.target.value
              viewStore.getState().setForecast({ ...choice, model, level: levelsFor(layer, model)[0] ?? 0 })
            }}>
              {availableModels.map((model) => <option key={model.id} value={model.id}>{model.label}</option>)}
            </select>
          </label>
          <p className="hazard-method">Threshold set: {products.data.threshold_version}. Values show the underlying forecast field; severity thresholds are interpretive guidance for screening.</p>
          {districtRisk.status === 'ready' && (
            <p className="hazard-method">District shading uses the {districtRisk.data.statistic.label.toLowerCase()}.</p>
          )}
          {districtRisk.status === 'error' && (
            <p className="deck-warning" role="alert">District risk shading could not load: {districtRisk.message}</p>
          )}
        </section>
      )}
    </div>
  )
}
