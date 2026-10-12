import { CloudSun, Layers } from 'lucide-react'
import type { ReactNode } from 'react'
import type { ForecastCatalogue, ForecastLayer } from '../api/types'
import type { ForecastTimesState } from '../data/useForecastTimes'
import {
  chooseLayer, chooseModel, formatRun, formatTime, hasData, levelLabel, levelsFor, type ForecastChoice,
} from '../forecast/choice'
import { useUi } from '../state/uiState'
import { useView, viewStore } from '../state/viewState'

const swatch = (layer: ForecastLayer) => `linear-gradient(to right, ${layer.colours.join(', ')})`

/** A row of buttons of which one is on: the models, or the pressure levels. */
function Choices({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="forecast-choices" role="group" aria-label={label}>
      <span className="forecast-choices-label">{label}</span>
      <div>{children}</div>
    </div>
  )
}

function whyNot(times: ForecastTimesState): string | null {
  if (times.status === 'loading') return 'Asking PMD which times it has…'
  if (times.status === 'ready' && times.times.length === 0) return 'PMD has no recent files for this choice.'
  if (times.status !== 'error') return null
  if (times.reason === 'not-configured') return 'The forecast source is not set up on this server.'
  if (times.reason === 'source-unreachable') return 'PMD’s server is not answering. Try again in a moment.'
  return `The forecast could not be loaded: ${times.message}`
}

/** What is on the map now, and the controls that change its model and level. */
function Showing({ forecast, layer, choice, times }: {
  forecast: ForecastCatalogue
  layer: ForecastLayer
  choice: ForecastChoice
  times: ForecastTimesState
}) {
  const tileError = useUi((s) => s.layerErrors.forecast ?? false)
  const fetching = useUi((s) => s.forecastLoading)
  const levels = levelsFor(layer, choice.model)
  const slot = times.status === 'ready' ? times.times.find((t) => t.time === choice.time) : undefined
  const problem = whyNot(times)
  const set = (next: ForecastChoice) => viewStore.getState().setForecast(next)
  return (
    <div className="forecast-showing">
      <div className="forecast-showing-head">
        <span className="layer-swatch" style={{ background: swatch(layer) }} aria-hidden />
        <strong>{layer.title}</strong>
        <button type="button" className="link-button" onClick={() => viewStore.getState().setForecast(null)}>
          Remove from map
        </button>
      </div>
      <Choices label="Model">
        {forecast.models.map((model) => {
          const offers = levelsFor(layer, model.id).length > 0
          return (
            <button
              key={model.id}
              type="button"
              aria-pressed={choice.model === model.id}
              disabled={!offers}
              title={offers ? undefined : `${model.label} has no ${layer.title.toLowerCase()}`}
              onClick={() => set(chooseModel(layer, model.id, choice))}
            >
              {model.label}
            </button>
          )
        })}
      </Choices>
      {levels.length > 1 && (
        <Choices label="Level">
          {levels.map((level) => (
            <button
              key={level}
              type="button"
              aria-pressed={choice.level === level}
              onClick={() => set({ ...choice, level })}
            >
              {levelLabel(level)}
            </button>
          ))}
        </Choices>
      )}
      {problem ? (
        <p className="forecast-status" role="status">{problem}</p>
      ) : (
        slot && (
          <p className="forecast-when">
            Forecast for <strong>{formatTime(slot.time)}</strong> Pakistan time
            <small>From the model run of {formatRun(slot.run)}</small>
          </p>
        )
      )}
      {!problem && !tileError && fetching && (
        <p className="forecast-fetching" role="status">Fetching this time from PMD…</p>
      )}
      {!problem && tileError && (
        <p className="forecast-status" role="alert">This time could not be fetched from PMD. Try another time.</p>
      )}
    </div>
  )
}

export function ForecastPanel({ forecast, times }: { forecast: ForecastCatalogue | null; times: ForecastTimesState }) {
  const choice = useView((s) => s.forecast)
  if (!forecast) return <p className="empty">Data not loaded yet</p>
  const chosenLayer = choice ? forecast.layers.find((l) => l.id === choice.layer) : undefined
  const toggle = (layer: ForecastLayer) =>
    viewStore.getState().setForecast(choice?.layer === layer.id ? null : chooseLayer(forecast, layer.id, choice))

  return (
    <>
      {!forecast.configured && (
        <p className="forecast-status" role="status">The forecast source is not set up on this server.</p>
      )}
      {choice && chosenLayer && (
        <section className="panel-part">
          <div className="part-head">
            <CloudSun size={19} aria-hidden />
            <h3>On the map</h3>
          </div>
          <Showing forecast={forecast} layer={chosenLayer} choice={choice} times={times} />
        </section>
      )}
      <section className="panel-part">
        <div className="part-head">
          <Layers size={19} aria-hidden />
          <h3>Layers</h3>
          <span className="part-count">{forecast.layers.filter(hasData).length}</span>
        </div>
        {forecast.groups.map((group) => {
          const layers = forecast.layers.filter((l) => l.group === group.id)
          if (layers.length === 0) return null
          return (
            <div key={group.id} className="layer-group">
              <h4>{group.title}</h4>
              {layers.map((layer) => {
                const ready = hasData(layer)
                const on = choice?.layer === layer.id
                return (
                  <label key={layer.id} className={`layer-switch${on ? ' on' : ''}${ready ? '' : ' disabled'}`}>
                    <span className="layer-swatch" style={{ background: swatch(layer) }} aria-hidden />
                    <span className="layer-name">
                      {layer.title}
                      {!ready && <small>No current data from PMD</small>}
                    </span>
                    <input
                      type="checkbox"
                      role="switch"
                      aria-label={layer.title}
                      disabled={!ready}
                      checked={on}
                      onChange={() => toggle(layer)}
                    />
                  </label>
                )
              })}
            </div>
          )
        })}
      </section>
    </>
  )
}
