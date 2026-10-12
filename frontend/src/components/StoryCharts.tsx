import { Table2 } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import type { ChartSpec } from '../api/types'
import { formatNumber } from '../charts/chartOption'
import { ICONS } from './MapPopup'

/** The frame every chart here shares: the headline, the drawing, a line of small print, and the table. */
function Shell({ spec, large, kind, children, table }: {
  spec: ChartSpec
  large: boolean
  kind: string
  children: ReactNode
  table: ReactNode
}) {
  return (
    <figure className={`chart ${kind}-chart${large ? ' chart-large' : ''}`} aria-label={spec.title}>
      <figcaption>
        <h4>{spec.title}</h4>
      </figcaption>
      {children}
      {spec.note && <p className="chart-note">{spec.note}</p>}
      <details className="chart-table">
        <summary title="Show table">
          <Table2 size={17} aria-hidden />
          <span>Show table</span>
        </summary>
        {table}
      </details>
    </figure>
  )
}

/**
 * Two shares for each row running opposite ways from a centre line. Rows are as thick as they are
 * weighty, so the big ones look big.
 */
export function DivergingChart({ spec, large = false }: { spec: ChartSpec; large?: boolean }) {
  const splits = spec.splits ?? []
  const [left, right] = spec.sides ?? [{ label: 'Left', colour: '#3b4cc0' }, { label: 'Right', colour: '#b40426' }]
  const heaviest = Math.max(0, ...splits.map((split) => split.weight))
  const thickness = (weight: number) =>
    (large ? 30 : 8) + (large ? 46 : 16) * (heaviest > 0 ? Math.sqrt(weight / heaviest) : 0)

  return (
    <Shell
      spec={spec}
      large={large}
      kind="diverging"
      table={
        <table>
          <thead>
            <tr>
              <th />
              <th>{left.label}</th>
              <th>{right.label}</th>
            </tr>
          </thead>
          <tbody>
            {splits.map((split) => (
              <tr key={split.name}>
                <th>{split.name}</th>
                <td>{formatNumber(split.left)}%</td>
                <td>{formatNumber(split.right)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      <div
        className="diverging"
        style={{ '--left': left.colour, '--right': right.colour } as CSSProperties}
        role="img"
        aria-label={splits
          .map((s) => `${s.name}: ${formatNumber(s.left)}% ${left.label}, ${formatNumber(s.right)}% ${right.label}`)
          .join('. ')}
      >
        <div className="diverging-row diverging-head">
          <span />
          <span className="diverging-side diverging-left">← {left.label}</span>
          <span className="diverging-side diverging-right">{right.label} →</span>
        </div>
        {splits.map((split, index) => (
          <div
            key={split.name}
            className={`diverging-row${split.highlight ? ' lead' : ''}`}
            style={{ '--row': index, '--thick': `${thickness(split.weight)}px` } as CSSProperties}
          >
            <span className="diverging-name">{split.name}</span>
            <div className="diverging-half diverging-left">
              <span className="diverging-bar" style={{ width: `${Math.min(100, split.left)}%` }}>
                <span className="diverging-value">{formatNumber(split.left)}%</span>
              </span>
            </div>
            <div className="diverging-half diverging-right">
              <span className="diverging-bar" style={{ width: `${Math.min(100, split.right)}%` }}>
                <span className="diverging-value">{formatNumber(split.right)}%</span>
              </span>
            </div>
          </div>
        ))}
      </div>
    </Shell>
  )
}

/**
 * How many times each thing was counted, out of a total: a picture and a name, a bar for the share,
 * and the count itself in large figures.
 */
export function CountsChart({ spec, large = false }: { spec: ChartSpec; large?: boolean }) {
  const items = spec.items ?? []
  const total = spec.total ?? 0
  const share = (value: number) => (total > 0 ? (value / total) * 100 : 0)

  return (
    <Shell
      spec={spec}
      large={large}
      kind="counts"
      table={
        <table>
          <thead>
            <tr>
              <th />
              <th>{spec.unit}</th>
              <th>Share</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.name}>
                <th>{item.name}</th>
                <td>{formatNumber(item.value)}</td>
                <td>{formatNumber(Math.round(share(item.value)))}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      <div
        className="counts"
        role="img"
        aria-label={items.map((item) => `${item.name}: ${item.value} of ${total} ${spec.unit}`).join('. ')}
      >
        {items.map((item, index) => {
          const Icon = item.icon ? ICONS[item.icon] : undefined
          return (
            <div
              key={item.name}
              className={`counts-row counts-${item.icon ?? 'plain'}${item.highlight ? ' lead' : ''}`}
              style={{ '--row': index } as CSSProperties}
            >
              <span className="counts-icon">{Icon && <Icon size={large ? 40 : 22} aria-hidden />}</span>
              <div className="counts-body">
                <span className="counts-name">{item.name}</span>
                <span className="counts-track" aria-hidden>
                  <span style={{ width: `${share(item.value)}%` }} />
                </span>
              </div>
              <span className="counts-value">
                <strong>{formatNumber(item.value)}</strong>
                <small>
                  of {formatNumber(total)} {spec.unit}
                </small>
              </span>
            </div>
          )
        })}
      </div>
    </Shell>
  )
}

/**
 * A whole and its parts: one strip divided up in the parts' colours, then each part on a line of
 * its own with a bar and its percentage, largest first.
 */
export function SharesChart({ spec, large = false }: { spec: ChartSpec; large?: boolean }) {
  const cells = spec.cells ?? []

  return (
    <Shell
      spec={spec}
      large={large}
      kind="shares"
      table={
        <table>
          <thead>
            <tr>
              <th />
              <th>Share</th>
            </tr>
          </thead>
          <tbody>
            {cells.map((cell) => (
              <tr key={cell.label}>
                <th>{cell.label}</th>
                <td>{formatNumber(cell.share)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      <div
        className="shares"
        role="img"
        aria-label={cells.map((cell) => `${cell.label} ${formatNumber(cell.share)}%`).join(', ')}
      >
        <div className="shares-whole">
          {cells.map((cell) => (
            <span
              key={cell.label}
              title={`${cell.label}: ${formatNumber(cell.share)}%`}
              style={{ flexGrow: cell.squares, background: cell.colour }}
            />
          ))}
        </div>
        <p className="shares-caption">The whole strip is all the land</p>
        {cells.map((cell, index) => (
          <div key={cell.label} className="shares-row" style={{ '--row': index, '--c': cell.colour } as CSSProperties}>
            <span className="shares-swatch" />
            <div className="shares-body">
              <span className="shares-name">{cell.label}</span>
              <span className="shares-track" aria-hidden>
                <span style={{ width: `${Math.min(100, cell.share)}%` }} />
              </span>
            </div>
            <strong className="shares-value">{formatNumber(cell.share)}%</strong>
          </div>
        ))}
      </div>
    </Shell>
  )
}
