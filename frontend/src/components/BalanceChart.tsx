import { Table2 } from 'lucide-react'
import { useState, type CSSProperties } from 'react'
import type { ChartSpec } from '../api/types'
import { formatNumber, markedYear } from '../charts/chartOption'

/** A round figure at or above the largest balance, for the two ends of the scale. */
function scaleEnd(largest: number): number {
  const step = [5, 10, 20, 25, 50, 100, 200, 250, 500].find((s) => largest / s <= 5) ?? 1000
  return Math.max(step, Math.ceil(largest / step) * step)
}

/**
 * A balance for each row in the year the portal is showing: bars run right of the centre line when
 * there is something to spare and left of it when there is a shortfall. The portal's year slider
 * moves it, and its play button runs it through the years; the bars glide from each year to the next.
 * Pointing at a row shows the sum behind it.
 */
export function BalanceChart({ spec, year, large = false }: { spec: ChartSpec; year: number | null; large?: boolean }) {
  const years = spec.categories.map(Number)
  const shown = markedYear(spec, year)
  const index = Math.max(0, shown === null ? years.length - 1 : years.indexOf(shown))
  const [pointed, setPointed] = useState<number | null>(null)

  const info = spec.balance
  const end = scaleEnd(Math.max(...spec.series.flatMap((series) => series.values.map((v) => Math.abs(v ?? 0)))))
  const ticks = [-end, -end / 2, 0, end / 2, end]
  const half = (value: number) => `${(Math.min(end, Math.abs(value)) / end) * 50}%`
  const inside = (value: number) => Math.abs(value) / end > 0.5
  const greenest = Math.max(1e-9, ...spec.series.map((series) => series.values[index] ?? 0))

  return (
    <figure className={large ? 'chart balance-chart chart-large' : 'chart balance-chart'} aria-label={spec.title}>
      <figcaption>
        <h4>{spec.title}</h4>
      </figcaption>

      <div className="balance" role="img" aria-label={`${years[index]}: ${spec.series
        .map((s) => `${s.name} ${formatNumber(s.values[index])}`)
        .join(', ')}`}>
        <div className="balance-plot">
          <span className="balance-zone balance-negative">{info?.negative ?? 'Shortfall'}</span>
          <span className="balance-zone balance-positive">{info?.positive ?? 'To spare'}</span>
          <span className="balance-zero">{info?.zero ?? ''}</span>
          <span className="balance-year" aria-hidden>{years[index]}</span>
          {ticks.map((tick) => (
            <span key={tick} className="balance-gridline" style={{ left: `${50 + (tick / end) * 50}%` }} />
          ))}
          <div className="balance-rows">
            {spec.series.map((series, row) => {
              const value = series.values[index] ?? 0
              const short = value < 0
              const available = info?.available?.[index]
              const needed = info?.needed?.[row]?.[index]
              return (
                <div
                  key={series.name}
                  className={`balance-row${pointed === row ? ' pointed' : ''}`}
                  tabIndex={0}
                  onMouseEnter={() => setPointed(row)}
                  onMouseLeave={() => setPointed(null)}
                  onFocus={() => setPointed(row)}
                  onBlur={() => setPointed(null)}
                >
                  <span className="balance-name">{series.name}</span>
                  <span
                    className={`balance-bar ${short ? 'short' : 'spare'}`}
                    style={{
                      width: half(value),
                      [short ? 'right' : 'left']: '50%',
                      '--strength': short ? 1 : 0.5 + 0.5 * (value / greenest),
                    } as CSSProperties}
                  />
                  <span
                    // A long bar carries its figure inside its end; a short one has it just beyond.
                    className={`balance-value ${short ? 'short' : 'spare'}${inside(value) ? ' inside' : ''}`}
                    style={
                      inside(value)
                        ? { [short ? 'left' : 'right']: `calc(50% - ${half(value)})` }
                        : { [short ? 'right' : 'left']: `calc(50% + ${half(value)})` }
                    }
                  >
                    {Math.abs(value).toFixed(1)}
                    <span className="balance-word"> {short ? (info?.negative_word ?? 'short') : (info?.positive_word ?? 'spare')}</span>
                  </span>
                  {pointed === row && available !== undefined && needed !== undefined && (
                    <span className="balance-sum">
                      {formatNumber(available)} available − {formatNumber(needed)} needed = {value > 0 ? '+' : ''}
                      {value.toFixed(1)}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
        <div className="balance-axis" aria-hidden>
          {ticks.map((tick) => (
            <span key={tick} style={{ left: `${50 + (tick / end) * 50}%` }}>
              {tick > 0 ? `+${formatNumber(tick)}` : formatNumber(tick)}
            </span>
          ))}
        </div>
      </div>

      {info?.caption && <p className="balance-caption">{info.caption}</p>}

      <details className="chart-table">
        <summary title="Show table">
          <Table2 size={17} aria-hidden />
          <span>Show table</span>
        </summary>
        <table>
          <thead>
            <tr>
              <th>Year</th>
              {spec.series.map((series) => (
                <th key={series.name}>{series.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {years.map((value, row) => (
              <tr key={value}>
                <th>{value}</th>
                {spec.series.map((series) => (
                  <td key={series.name}>{formatNumber(series.values[row])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  )
}
