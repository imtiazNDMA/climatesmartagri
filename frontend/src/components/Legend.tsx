import type { Catalogue, Legend as LegendSpec } from '../api/types'
import { legendValues, levelLabel, levelsFor } from '../forecast/choice'
import { effectiveYear } from '../state/selectors'
import { useView } from '../state/viewState'

function Key({ legend }: { legend: LegendSpec }) {
  if (legend.type === 'classes') {
    return (
      <ul className="legend-classes">
        {legend.items.map((item) => (
          <li key={item.label}>
            <span className="legend-swatch" style={{ background: item.colour }} />
            {item.label}
          </li>
        ))}
      </ul>
    )
  }
  return (
    <div className="legend-ramp">
      <span className="legend-bar" style={{ background: `linear-gradient(to right, ${legend.colours.join(', ')})` }} />
      <span className="legend-ends">
        <span>{legend.min_label || 'Low'}</span>
        <span>{legend.max_label || 'High'}</span>
      </span>
    </div>
  )
}

/** The forecast's key: its colours with the values at each end, and which model and level it is for. */
function ForecastKey({ catalogue, named }: { catalogue: Catalogue; named: boolean }) {
  const choice = useView((s) => s.forecast)
  const layer = catalogue.forecast?.layers.find((l) => l.id === choice?.layer)
  if (!choice || !layer) return null
  const model = catalogue.forecast?.models.find((m) => m.id === choice.model)
  const values = legendValues(layer, choice.level, choice.model)
  // Two values carry the unit themselves; a row of them leaves it to the heading.
  const many = values.length > 2
  const unit = layer.unit && !many ? ` ${layer.unit}` : ''
  return (
    <div className="legend-entry">
      <h4>
        {layer.title}
        {/* The level is named only where there is a choice of them. */}
        {choice.level !== 0 && levelsFor(layer, choice.model).length > 1 && `, ${levelLabel(choice.level)}`}
        {many && layer.unit && ` (${layer.unit})`}
        {named && model && ` · ${model.label}`}
      </h4>
      <div className="legend-ramp">
        <span className="legend-bar" style={{ background: `linear-gradient(to right, ${layer.colours.join(', ')})` }} />
        <span className={many ? 'legend-ends legend-stops' : 'legend-ends'}>
          {values.map((value) => (
            <span key={value}>{`${value}${unit}`}</span>
          ))}
        </span>
      </div>
    </div>
  )
}

export function Legend({ catalogue }: { catalogue: Catalogue }) {
  const layers = useView((s) => s.layers)
  const year = useView((s) => s.year)
  const forecastOn = useView((s) => s.forecast !== null)
  if (!layers.length && !forecastOn) return null

  return (
    <section className="legend" aria-label="Legend">
      <h3>Legend</h3>
      {forecastOn && <ForecastKey catalogue={catalogue} named />}
      {layers.map((active) => {
        const layer = catalogue.layers.find((l) => l.id === active.id)
        if (!layer?.legend) return null
        const shownYear = effectiveYear(layer.years, year)
        return (
          <div key={layer.id} className={active.hidden ? 'legend-entry legend-hidden' : 'legend-entry'}>
            {/* One layer needs no name here; several do, and so does a layer shown for one year. */}
            {(layers.length > 1 || shownYear !== null) && (
              <h4>{shownYear === null ? layer.title : `${layer.title} (${shownYear})`}</h4>
            )}
            <Key legend={layer.legend} />
          </div>
        )
      })}
    </section>
  )
}
