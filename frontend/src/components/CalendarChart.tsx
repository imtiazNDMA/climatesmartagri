import type { CalendarDates, ChartSpec } from '../api/types'
import { barPosition, describeRanges, MONTH_LETTERS, yearFraction } from '../charts/calendar'

function Lane({ dates, which }: { dates: CalendarDates; which: 'traditional' | 'adjusted' }) {
  const label = which === 'traditional' ? 'Traditional' : 'Climate-smart'
  const stages = [
    { name: 'sowing', ranges: dates.sowing },
    { name: 'harvest', ranges: dates.harvest },
  ]
  const hasMonths = dates.sowing.length + dates.harvest.length > 0
  return (
    <div className={`calendar-lane calendar-${which}`}>
      {hasMonths ? (
        stages.flatMap((stage) =>
          stage.ranges.map((range, index) => (
            <span
              key={`${stage.name}-${index}`}
              className={`calendar-bar calendar-${stage.name}`}
              style={barPosition(range)}
              role="img"
              aria-label={`${label} ${stage.name}: ${describeRanges(stage.ranges)}`}
              title={`${label} ${stage.name}: ${describeRanges(stage.ranges)}`}
            />
          )),
        )
      ) : (
        // A calendar given in words, with no months to draw.
        <span className="calendar-words">{dates.text}</span>
      )}
    </div>
  )
}

/**
 * A crop calendar: the year across the top, and for each crop its traditional dates above its
 * climate-smart dates, so a shift shows as two bars that no longer line up.
 */
export function CalendarChart({ spec, large = false }: { spec: ChartSpec; large?: boolean }) {
  const rows = spec.rows ?? []
  const today = `${+(yearFraction(new Date()) * 100).toFixed(2)}%`

  return (
    <figure className={large ? 'chart calendar-chart chart-large' : 'chart calendar-chart'} aria-label={spec.title}>
      <figcaption>
        <h4>{spec.title}</h4>
        {spec.subtitle && <p className="chart-subtitle">{spec.subtitle}</p>}
      </figcaption>

      <ul className="calendar-key" aria-label="Key">
        <li><span className="calendar-swatch calendar-sowing" /> Sowing</li>
        <li><span className="calendar-swatch calendar-harvest" /> Harvest</li>
        <li><span className="calendar-swatch calendar-sowing calendar-swatch-faded" /> Traditional (top line)</li>
        <li><span className="calendar-swatch calendar-today" /> Today</li>
      </ul>

      <div className="calendar-grid">
        <div className="calendar-head">
          <span />
          <div className="calendar-months">
            {MONTH_LETTERS.map((letter, month) => (
              <span key={month} className="calendar-month">
                {letter}
              </span>
            ))}
          </div>
        </div>
        {rows.map((row) => (
          <div key={row.crop} className="calendar-row">
            <div className="calendar-crop">
              <strong>{row.crop}</strong>
              {row.sown_earlier ? (
                <span className="calendar-badge calendar-badge-earlier">Sow earlier</span>
              ) : row.changed ? (
                <span className="calendar-badge">Adjusted</span>
              ) : (
                <span className="calendar-badge calendar-badge-same">No change</span>
              )}
            </div>
            <div className="calendar-track">
              <Lane dates={row.traditional} which="traditional" />
              <Lane dates={row.adjusted} which="adjusted" />
              <span className="calendar-now" style={{ left: today }} aria-hidden />
            </div>
            {large && <p className="calendar-reason">{row.reason}</p>}
          </div>
        ))}
      </div>

      <details className="chart-table">
        <summary>Show table</summary>
        <table>
          <thead>
            <tr>
              <th>Crop</th>
              <th>Traditional</th>
              <th>Climate-smart</th>
              <th>Why</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.crop}>
                <th>{row.crop}</th>
                <td>{row.traditional.text}</td>
                <td>{row.adjusted.text}</td>
                <td>{row.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  )
}
