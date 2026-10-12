import { Table2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import type { ChartSpec } from '../api/types'
import { formatNumber, markedYear } from '../charts/chartOption'
import { bandPath, linePath, linear, nearestIndex, niceScale, tickYears, type Point } from '../charts/outlook'
import { balanceColour, balanceOf, breakEven, efficiencySteps, firstDeficitYear, needAt } from '../charts/water'
import { uiStore, useUi } from '../state/uiState'
import { viewStore } from '../state/viewState'

const one = (value: number | null | undefined) => (value === null || value === undefined ? '–' : value.toFixed(1))
const signed = (value: number | null | undefined) =>
  value === null || value === undefined ? '–' : `${value > 0 ? '+' : value < 0 ? '−' : ''}${Math.abs(value).toFixed(1)}`

/** A drawing's width, and how much of the window is left below where it starts, kept up as either changes. */
function useFrame() {
  const frame = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 0, room: 0 })
  useEffect(() => {
    const measure = () => {
      if (!frame.current) return
      const box = frame.current.getBoundingClientRect()
      // Room: the window below the drawing's top, less the year slider and the table link.
      setSize({ width: Math.round(box.width), room: Math.round(window.innerHeight - box.top - 150) })
    }
    const watch = new ResizeObserver(measure)
    if (frame.current) watch.observe(frame.current)
    window.addEventListener('resize', measure)
    return () => {
      watch.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [])
  return { frame, ...size }
}

/** What both water charts read from a chart's description: the years, the two series and the efficiencies. */
function useWater(spec: ChartSpec, year: number | null) {
  const years = useMemo(() => spec.categories.map(Number), [spec.categories])
  const [available, needAtBase] = spec.series
  const range = spec.efficiency ?? { min: 35, max: 70, base: 35, start: 45, given: [35, 50, 70] }
  const efficiency = useUi((s) => s.efficiency) ?? range.start
  const marked = markedYear(spec, year)
  const chosen = Math.max(0, marked === null ? years.length - 1 : years.indexOf(marked))
  return { years, available: available.values, needAtBase: needAtBase.values, range, efficiency, chosen }
}

const setEfficiency = (value: number) => uiStore.getState().setEfficiency(value)
const setYear = (value: number) => viewStore.getState().setYear(value)

function TableOf({ spec, years, columns }: { spec: ChartSpec; years: number[]; columns: { name: string; values: (number | null)[] }[] }) {
  return (
    <>
      {spec.note && <p className="chart-note">{spec.note}</p>}
      <details className="chart-table">
        <summary title="Show table">
          <Table2 size={17} aria-hidden />
          <span>Show table</span>
        </summary>
        <table>
          <thead>
            <tr>
              <th scope="col">Year</th>
              {columns.map((column) => (
                <th key={column.name} scope="col">{column.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {years.map((value, i) => (
              <tr key={value}>
                <th scope="row">{value}</th>
                {columns.map((column) => (
                  <td key={column.name}>{one(column.values[i])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </>
  )
}

/**
 * The water available against the water crops need, at whatever irrigation efficiency the reader sets.
 * The space between the two lines is the balance: green where there is water to spare, red where there is
 * not. Dragging the efficiency moves the need line, and with it the year the water first runs short.
 */
export function EfficiencyExplorer({ spec, year, large = false }: { spec: ChartSpec; year: number | null; large?: boolean }) {
  const { frame, width, room } = useFrame()
  const { years, available, needAtBase, range, efficiency, chosen } = useWater(spec, year)
  const [pointed, setPointed] = useState<number | null>(null)
  const at = pointed ?? chosen
  const last = years.length - 1

  const need = useMemo(() => needAt(needAtBase, range.base, efficiency), [needAtBase, range.base, efficiency])
  const balance = useMemo(() => balanceOf(available, need), [available, need])
  const shortFrom = firstDeficitYear(years, balance)

  const height = large ? Math.max(300, Math.min(560, Math.round(width * 0.42), room)) : 280
  // Named line ends need room: with two charts side by side, as in the panel, the value stands alone.
  const roomy = large && width >= 760
  const pad = { top: 16, right: roomy ? 250 : large ? 112 : 84, bottom: 32, left: large ? 52 : 40 }
  const fontSize = large ? 17 : 13
  // The scale takes in the need at both ends of the efficiency range, so the lines move and the axis does not.
  const scale = useMemo(() => {
    const all = [...needAt(needAtBase, range.base, range.min), ...needAt(needAtBase, range.base, range.max), ...available]
      .filter((v): v is number => v !== null)
    return niceScale(Math.min(...all), Math.max(...all), large ? 7 : 5)
  }, [needAtBase, available, range, large])
  const x = linear(0, Math.max(1, last), pad.left, Math.max(pad.left + 1, width - pad.right))
  const y = linear(scale.min, scale.max, height - pad.bottom, pad.top)
  const points = (values: (number | null)[]): Point[] => values.map((value, i) => ({ x: x(i), y: y(value ?? scale.min) }))
  const [supply, demand] = [points(available), points(need)]
  const plotLeft = pad.left
  const plotRight = width - pad.right
  // The balance is one shape between the two lines, coloured red above the supply line and green below it.
  const above = `M${plotLeft},${pad.top} ${supply.map((p) => `L${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')} L${plotRight},${pad.top} Z`
  const below = `M${plotLeft},${height - pad.bottom} ${supply.map((p) => `L${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')} L${plotRight},${height - pad.bottom} Z`
  const clip = `water-${spec.id}-${large ? 'large' : 'small'}`

  const pointAt = (event: PointerEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect()
    setPointed(nearestIndex(supply.map((p) => p.x), event.clientX - box.left))
  }
  const onKey = (event: KeyboardEvent<SVGSVGElement>) => {
    const held = years.indexOf(viewStore.getState().year ?? NaN)
    const now = held >= 0 ? held : chosen
    const steps: Record<string, number> = { ArrowLeft: now - 1, ArrowRight: now + 1, Home: 0, End: last }
    if (!(event.key in steps)) return
    event.preventDefault()
    setYear(years[Math.min(last, Math.max(0, steps[event.key]))])
  }
  const short = (balance[at] ?? 0) < 0
  // The two lines often end close together. Their labels are set clear of the cursor's badge, and pushed
  // apart about the midpoint when they would otherwise sit on top of each other.
  const endX = supply[last].x + (large ? 48 : 34)
  const clear = width < 620 ? 3 : 2
  const apart = roomy ? 52 : large ? 26 : 20
  const crowd = Math.max(0, apart - Math.abs(supply[last].y - demand[last].y)) / 2
  const supplyBelow = supply[last].y >= demand[last].y
  const supplyEnd = supply[last].y + (supplyBelow ? crowd : -crowd)
  const demandEnd = demand[last].y + (supplyBelow ? -crowd : crowd)

  return (
    <figure className={`chart explorer-chart${large ? ' chart-large' : ''}`} aria-label={spec.title}>
      <figcaption>
        <h4>{spec.title}</h4>
      </figcaption>

      <div className="explorer-top">
        <label className="explorer-dial">
          <span>Irrigation efficiency</span>
          <strong>{efficiency}%</strong>
          <input
            type="range" min={range.min} max={range.max} step={1} value={efficiency}
            aria-label="Irrigation efficiency" aria-valuetext={`${efficiency} percent`}
            onChange={(event) => setEfficiency(Number(event.target.value))}
          />
          <span className="explorer-marks" aria-hidden>
            {range.given.map((given) => (
              <i key={given} style={{ left: `${((given - range.min) / (range.max - range.min)) * 100}%` }}>{given}%</i>
            ))}
          </span>
        </label>
        <div className="explorer-readout" aria-live="polite">
          <div><span>{years[at]}</span><b>{one(available[at])}</b><small>water available</small></div>
          <div><span>at {efficiency}%</span><b>{one(need[at])}</b><small>water crops need</small></div>
          <div className={short ? 'short' : 'spare'}>
            <span>{short ? 'Deficit' : 'Buffer'}</span><b>{signed(balance[at])}</b><small>balance</small>
          </div>
          <div className={shortFrom === null ? 'spare' : 'short'}>
            <span>{shortFrom === null ? 'Enough' : 'Short from'}</span>
            <b>{shortFrom ?? `to ${years[last]}`}</b>
            <small>{shortFrom === null ? 'in every year' : 'first year of deficit'}</small>
          </div>
        </div>
      </div>

      <div ref={frame} className="explorer-frame">
        {width > 0 && (
          <svg
            width={width} height={height} role="img" tabIndex={0}
            aria-label={`At ${efficiency}% efficiency in ${years[at]}: ${one(available[at])} available, ${one(need[at])} needed, balance ${signed(balance[at])}. Arrow keys change the year.`}
            onPointerMove={pointAt}
            onPointerLeave={() => setPointed(null)}
            onClick={() => pointed !== null && setYear(years[pointed])}
            onKeyDown={onKey}
          >
            <defs>
              <clipPath id={`${clip}-above`}><path d={above} /></clipPath>
              <clipPath id={`${clip}-below`}><path d={below} /></clipPath>
            </defs>
            {scale.ticks.map((tick) => (
              <g key={tick} className="outlook-grid">
                <line x1={plotLeft} x2={plotRight} y1={y(tick)} y2={y(tick)} />
                <text x={plotLeft - 8} y={y(tick)} dy="0.34em" textAnchor="end" fontSize={fontSize - 2}>{formatNumber(tick)}</text>
              </g>
            ))}
            {tickYears(years, 5, clear).map((tick) => (
              <text key={tick} className="outlook-year" x={x(years.indexOf(tick))} y={height - pad.bottom + 21} textAnchor="middle" fontSize={fontSize - 2}>
                {tick}
              </text>
            ))}

            <path className="explorer-band short" d={bandPath(demand, supply)} clipPath={`url(#${clip}-above)`} />
            <path className="explorer-band spare" d={bandPath(demand, supply)} clipPath={`url(#${clip}-below)`} />

            {/* The need at the three efficiencies the source gives, faintly, to place the chosen one among them. */}
            {range.given.filter((given) => given !== efficiency).map((given) => {
              const line = points(needAt(needAtBase, range.base, given))
              return (
                <g key={given} className="explorer-given">
                  <path d={linePath(line)} />
                  <text x={line[0].x + 6} y={line[0].y - 6} fontSize={fontSize - 4}>{given}%</text>
                </g>
              )
            })}

            <path className="explorer-line supply" d={linePath(supply)} />
            <path className="explorer-line demand" d={linePath(demand)} />

            {shortFrom !== null && shortFrom !== years[0] && (
              <g className="explorer-flag" transform={`translate(${x(years.indexOf(shortFrom)).toFixed(1)} 0)`}>
                <line y1={pad.top} y2={height - pad.bottom} />
                <text x={6} y={pad.top + fontSize} fontSize={fontSize - 2}>Short from {shortFrom}</text>
              </g>
            )}

            <g className="outlook-end" transform={`translate(${endX.toFixed(1)} ${supplyEnd.toFixed(1)})`}>
              {roomy && <text dy="-0.15em" fontSize={fontSize - 1}>Water available</text>}
              <text className="outlook-end-value" dy={roomy ? '1em' : '0.36em'} fontSize={fontSize + (large ? 4 : 1)}>{one(available[last])}</text>
            </g>
            <g className="outlook-end" transform={`translate(${endX.toFixed(1)} ${demandEnd.toFixed(1)})`}>
              {roomy && <text dy="-0.15em" fontSize={fontSize - 1}>Needed at {efficiency}%</text>}
              <text className="outlook-end-value" dy={roomy ? '1em' : '0.36em'} fontSize={fontSize + (large ? 4 : 1)}>{one(need[last])}</text>
            </g>

            <g className="outlook-cursor" style={{ transform: `translateX(${supply[at].x.toFixed(1)}px)` }}>
              <line y1={pad.top} y2={height - pad.bottom} />
              <line className={`explorer-span ${short ? 'short' : 'spare'}`} y1={supply[at].y} y2={demand[at].y} />
              <circle className="explorer-dot supply" cy={supply[at].y} r={large ? 6.5 : 5} />
              <circle className="explorer-dot demand" cy={demand[at].y} r={large ? 6.5 : 5} />
              <g className={`explorer-badge ${short ? 'short' : 'spare'}`} transform={`translate(0 ${((supply[at].y + demand[at].y) / 2).toFixed(1)})`}>
                <rect x={large ? -36 : -27} y={large ? -15 : -12} width={large ? 72 : 54} height={large ? 30 : 24} rx={large ? 15 : 12} />
                <text dy="0.36em" textAnchor="middle" fontSize={fontSize - 2}>{signed(balance[at])}</text>
              </g>
            </g>
          </svg>
        )}
      </div>

      <TableOf
        spec={spec} years={years}
        columns={[
          { name: 'Water available', values: available },
          { name: `Water crops need at ${efficiency}%`, values: need },
          { name: 'Balance', values: balance },
        ]}
      />
    </figure>
  )
}

/**
 * Every efficiency against every year at once: a grid of cells, green where the water is enough and red
 * where it is not. The line through it is the efficiency that just breaks even, which is the least that
 * is enough in each year. Clicking a cell takes the explorer to that efficiency and the portal to that year.
 */
export function EfficiencyGrid({ spec, year, large = false }: { spec: ChartSpec; year: number | null; large?: boolean }) {
  const { frame, width, room } = useFrame()
  const { years, available, needAtBase, range, efficiency, chosen } = useWater(spec, year)
  const [pointed, setPointed] = useState<{ row: number; col: number } | null>(null)
  const last = years.length - 1

  const rows = useMemo(() => efficiencySteps(range.min, range.max, large ? 2.5 : 5).reverse(), [range, large])
  const cells = useMemo(
    () => rows.map((level) => balanceOf(available, needAt(needAtBase, range.base, level))),
    [rows, available, needAtBase, range.base],
  )
  const most = useMemo(() => Math.max(1, ...cells.flat().map((v) => Math.abs(v ?? 0))), [cells])
  const even = useMemo(() => breakEven(needAtBase, range.base, available), [needAtBase, range.base, available])

  const height = large ? Math.max(300, Math.min(560, Math.round(width * 0.42), room)) : 250
  const pad = { top: 10, right: large ? 20 : 8, bottom: 32, left: large ? 64 : 44 }
  const fontSize = large ? 16 : 12
  const cellW = Math.max(1, (width - pad.left - pad.right) / years.length)
  const cellH = (height - pad.top - pad.bottom) / rows.length
  const step = rows.length > 1 ? rows[0] - rows[1] : 5
  // A cell stands for the efficiency at its middle, so the scale runs half a step past each end.
  const yOf = linear(range.max + step / 2, range.min - step / 2, pad.top, height - pad.bottom)
  const line = even.map((value, i) => ({ x: pad.left + (i + 0.5) * cellW, y: yOf(Math.min(range.max, Math.max(range.min, value ?? range.min))) }))
  const shownRow = pointed?.row ?? rows.reduce((best, level, i) => (Math.abs(level - efficiency) < Math.abs(rows[best] - efficiency) ? i : best), 0)
  const shownCol = pointed?.col ?? chosen
  const value = cells[shownRow]?.[shownCol] ?? null

  return (
    <figure className={`chart grid-chart${large ? ' chart-large' : ''}`} aria-label={spec.title}>
      <figcaption>
        <h4>{spec.title}</h4>
      </figcaption>

      <div className="grid-readout" aria-live="polite">
        <strong>{rows[shownRow]}%</strong>
        <span>efficiency in <b>{years[shownCol]}</b></span>
        <em className={(value ?? 0) < 0 ? 'short' : 'spare'}>
          {(value ?? 0) < 0 ? 'Deficit' : 'Buffer'} {signed(value)}
        </em>
        <span className="grid-even">Breaks even at <b>{one(even[shownCol])}%</b></span>
        <span className="grid-key" aria-hidden>
          <i style={{ background: `linear-gradient(90deg, ${balanceColour(-most, most)}, ${balanceColour(-0.01, most)})` }} />
          deficit
          <i style={{ background: `linear-gradient(90deg, ${balanceColour(0.01, most)}, ${balanceColour(most, most)})` }} />
          buffer
        </span>
      </div>

      <div ref={frame} className="grid-frame">
        {width > 0 && (
          <svg width={width} height={height} role="img" aria-label={`Water balance for efficiencies from ${range.min}% to ${range.max}%, ${years[0]} to ${years[last]}`} onPointerLeave={() => setPointed(null)}>
            {rows.map((level, row) => (
              <g key={level}>
                {(large ? level % 5 === 0 : true) && (
                  <text className="outlook-year" x={pad.left - 8} y={pad.top + (row + 0.5) * cellH} dy="0.34em" textAnchor="end" fontSize={fontSize - 1}>
                    {level}%
                  </text>
                )}
                {years.map((cellYear, col) => (
                  <rect
                    key={cellYear}
                    className="grid-cell"
                    style={{ animationDelay: `${col * 14}ms` }}
                    x={pad.left + col * cellW + 0.75} y={pad.top + row * cellH + 0.75}
                    width={Math.max(0, cellW - 1.5)} height={Math.max(0, cellH - 1.5)} rx={large ? 4 : 2.5}
                    fill={balanceColour(cells[row][col], most)}
                    onPointerEnter={() => setPointed({ row, col })}
                    onClick={() => {
                      setEfficiency(Math.round(level))
                      setYear(cellYear)
                    }}
                  >
                    <title>{`${level}% in ${cellYear}: ${signed(cells[row][col])}`}</title>
                  </rect>
                ))}
              </g>
            ))}
            {tickYears(years, 5, width < 620 ? 3 : 2).map((tick) => (
              <text key={tick} className="outlook-year" x={pad.left + (years.indexOf(tick) + 0.5) * cellW} y={height - pad.bottom + 21} textAnchor="middle" fontSize={fontSize - 1}>
                {tick}
              </text>
            ))}

            {/* The year and the efficiency in hand, ringed. */}
            <rect className="grid-column" x={pad.left + shownCol * cellW} y={pad.top} width={cellW} height={height - pad.top - pad.bottom} rx={large ? 5 : 3} />
            <rect className="grid-row" x={pad.left} y={pad.top + shownRow * cellH} width={width - pad.left - pad.right} height={cellH} rx={large ? 5 : 3} />

            <path className="grid-even-line under" d={linePath(line)} />
            <path className="grid-even-line" d={linePath(line)} />
            <text className="grid-even-label" x={line[last].x - 8} y={line[last].y - (large ? 12 : 9)} textAnchor="end" fontSize={fontSize}>
              Break-even {one(even[last])}%
            </text>
            <text className="grid-even-label" x={line[0].x + 8} y={line[0].y + (large ? 24 : 18)} fontSize={fontSize}>
              {one(even[0])}%
            </text>
          </svg>
        )}
      </div>

      <TableOf
        spec={spec} years={years}
        columns={[
          { name: 'Break-even efficiency, %', values: even },
          ...[...rows].reverse().filter((level) => level % 5 === 0).map((level) => ({
            name: `Balance at ${level}%`,
            values: balanceOf(available, needAt(needAtBase, range.base, level)),
          })),
        ]}
      />
    </figure>
  )
}
