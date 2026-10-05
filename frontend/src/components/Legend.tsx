import type { Catalogue, Legend as LegendSpec } from '../api/types'
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
      <span>
        {legend.min} – {legend.max} {legend.unit}
      </span>
    </div>
  )
}

export function Legend({ catalogue }: { catalogue: Catalogue }) {
  const layers = useView((s) => s.layers)
  const year = useView((s) => s.year)
  if (!layers.length) return null

  return (
    <section className="legend" aria-label="Legend">
      {layers.map((active) => {
        const layer = catalogue.layers.find((l) => l.id === active.id)
        if (!layer?.legend) return null
        const shownYear = effectiveYear(layer.years, year)
        return (
          <div key={layer.id} className={active.hidden ? 'legend-entry legend-hidden' : 'legend-entry'}>
            <h4>{shownYear === null ? layer.title : `${layer.title} (${shownYear})`}</h4>
            <Key legend={layer.legend} />
          </div>
        )
      })}
    </section>
  )
}
