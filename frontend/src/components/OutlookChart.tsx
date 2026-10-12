import { Table2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import type { ChartSpec } from '../api/types'
import { formatNumber, markedYear } from '../charts/chartOption'
import { bandPath, difference, linePath, linear, nearestIndex, niceScale, tickYears, type Point } from '../charts/outlook'
import { viewStore } from '../state/viewState'

const one = (value: number | null | undefined) =>
  value === null || value === undefined ? '–' : value.toFixed(1)

/**
 * Food needed against food available two ways, over the years: three lines, with the space between them
 * filled in, because the spaces are the story. The upper band is the gap that remains even with climate
 * smart agriculture; the lower is what climate smart agriculture adds over traditional farming.
 *
 * Pointing at a year reads it out; clicking, or the arrow keys, moves the portal to that year. The two
 * bands can be switched off, and every year's figures written on.
 */
export function OutlookChart({ spec, year, large = false }: { spec: ChartSpec; year: number | null; large?: boolean }) {
  const frame = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  const [room, setRoom] = useState(0)
  const [pointed, setPointed] = useState<number | null>(null)
  const [show, setShow] = useState({ gap: true, gain: true, every: large })

  useEffect(() => {
    if (!frame.current) return
    const measure = () => {
      if (!frame.current) return
      const box = frame.current.getBoundingClientRect()
      setWidth(Math.round(box.width))
      // What is left of the window below where the drawing starts, less the year slider and the table link.
      setRoom(Math.round(window.innerHeight - box.top - 150))
    }
    const watch = new ResizeObserver(measure)
    watch.observe(frame.current)
    window.addEventListener('resize', measure)
    return () => {
      watch.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [])

  const years = useMemo(() => spec.categories.map(Number), [spec.categories])
  const [needed, smart, usual] = spec.series
  const gap = useMemo(() => difference(needed.values, smart.values), [needed, smart])
  const gain = useMemo(() => difference(smart.values, usual.values), [smart, usual])
  const marked = markedYear(spec, year)
  const chosen = Math.max(0, marked === null ? years.length - 1 : years.indexOf(marked))
  const at = pointed ?? chosen

  // Enlarged, the drawing takes what is left of the window under its headline, readout and switches.
  const height = large ? Math.max(320, Math.min(620, Math.round(width * 0.46), room)) : 300
  // Named line ends need room: with two charts side by side, as in the panel, the value stands alone.
  const roomy = large && width >= 760
  const pad = { top: 18, right: roomy ? 288 : large ? 96 : 70, bottom: 34, left: large ? 52 : 40 }
  const scale = useMemo(() => {
    const all = spec.series.flatMap((series) => series.values.filter((v): v is number => v !== null))
    return niceScale(Math.min(...all), Math.max(...all), large ? 7 : 5)
  }, [spec.series, large])
  const x = linear(0, Math.max(1, years.length - 1), pad.left, Math.max(pad.left + 1, width - pad.right))
  const y = linear(scale.min, scale.max, height - pad.bottom, pad.top)
  const points = (values: (number | null)[]): Point[] => values.map((value, i) => ({ x: x(i), y: y(value ?? scale.min) }))
  const [top, middle, bottom] = [points(needed.values), points(smart.values), points(usual.values)]
  const last = years.length - 1
  const fontSize = large ? 17 : 13
  // A figure for every year only where the years are far enough apart for the badges not to run together;
  // otherwise for every second or third year, however many it takes.
  const everyStep = Math.max(1, Math.ceil(((large ? 15 : 12) * 2 + 4) / Math.max(1, x(1) - x(0))))

  const pointAt = (event: PointerEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect()
    setPointed(nearestIndex(top.map((p) => p.x), event.clientX - box.left))
  }
  const move = (to: number) => viewStore.getState().setYear(years[Math.min(last, Math.max(0, to))])
  const onKey = (event: KeyboardEvent<SVGSVGElement>) => {
    // From the year the portal holds now, not the one last drawn: keys can arrive faster than the chart redraws.
    const held = years.indexOf(viewStore.getState().year ?? NaN)
    const now = held >= 0 ? held : chosen
    const steps: Record<string, number> = { ArrowLeft: now - 1, ArrowRight: now + 1, Home: 0, End: last }
    if (!(event.key in steps)) return
    event.preventDefault()
    move(steps[event.key])
  }

  const toggles: { key: keyof typeof show; label: string; tone: string }[] = [
    { key: 'gap', label: 'Food gap', tone: 'gap' },
    { key: 'gain', label: 'Gain from climate smart agriculture', tone: 'gain' },
    { key: 'every', label: 'Figures for every year', tone: 'plain' },
  ]
  const badge = (cx: number, cy: number, value: number | null, tone: 'gap' | 'gain', big: boolean) => {
    const r = big ? (large ? 21 : 16) : large ? 15 : 12
    return (
      <g className={`outlook-badge outlook-${tone}${big ? ' big' : ''}`} transform={`translate(${cx.toFixed(1)} ${cy.toFixed(1)})`}>
        <circle r={r} />
        <text dy="0.36em" textAnchor="middle" fontSize={big ? fontSize - 2 : fontSize - 5}>{one(value)}</text>
      </g>
    )
  }

  return (
    <figure className={`chart outlook-chart${large ? ' chart-large' : ''}`} aria-label={spec.title}>
      <figcaption>
        <h4>{spec.title}</h4>
      </figcaption>

      {/* The year under the pointer, or the portal's year, read out in full. */}
      <div className="outlook-readout" aria-live="polite">
        <strong>{years[at]}</strong>
        <dl>
          <div className="outlook-needed"><dt>{needed.name}</dt><dd>{one(needed.values[at])}</dd></div>
          <div className="outlook-smart"><dt>{smart.name}</dt><dd>{one(smart.values[at])}</dd></div>
          <div className="outlook-usual"><dt>{usual.name}</dt><dd>{one(usual.values[at])}</dd></div>
          <div className="outlook-gap"><dt>Food gap</dt><dd>{one(gap[at])}</dd></div>
          <div className="outlook-gain"><dt>Gain</dt><dd>{one(gain[at])}</dd></div>
        </dl>
      </div>

      <div className="outlook-toggles" role="group" aria-label="What the chart shows">
        {toggles.map((toggle) => (
          <button
            key={toggle.key}
            type="button"
            className={`outlook-toggle outlook-${toggle.tone}`}
            aria-pressed={show[toggle.key]}
            onClick={() => setShow((s) => ({ ...s, [toggle.key]: !s[toggle.key] }))}
          >
            <i aria-hidden />
            {toggle.label}
          </button>
        ))}
      </div>

      <div ref={frame} className="outlook-frame">
        {width > 0 && (
          <svg
            width={width} height={height} role="img" tabIndex={0}
            aria-label={`${years[at]}: ${needed.name} ${one(needed.values[at])}, ${smart.name} ${one(smart.values[at])}, ${usual.name} ${one(usual.values[at])}. Arrow keys change the year.`}
            onPointerMove={pointAt}
            onPointerLeave={() => setPointed(null)}
            onClick={() => pointed !== null && move(pointed)}
            onKeyDown={onKey}
          >
            {scale.ticks.map((tick) => (
              <g key={tick} className="outlook-grid">
                <line x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} />
                <text x={pad.left - 8} y={y(tick)} dy="0.34em" textAnchor="end" fontSize={fontSize - 2}>{formatNumber(tick)}</text>
              </g>
            ))}
            {tickYears(years, 5, width < 620 ? 3 : 2).map((tick) => (
              <text
                key={tick} className="outlook-year" x={x(years.indexOf(tick))} y={height - pad.bottom + 22}
                textAnchor="middle" fontSize={fontSize - 2}
              >
                {tick}
              </text>
            ))}

            {show.gap && <path className="outlook-band outlook-gap" d={bandPath(top, middle)} />}
            {show.gain && <path className="outlook-band outlook-gain" d={bandPath(middle, bottom)} />}

            <path className="outlook-line outlook-usual" d={linePath(bottom)} pathLength={1} />
            <path className="outlook-line outlook-smart" d={linePath(middle)} pathLength={1} />
            <path className="outlook-line outlook-needed" d={linePath(top)} pathLength={1} />

            {show.every && years.map((_, i) =>
              i % everyStep === 0 && i !== at ? (
                <g key={i} className="outlook-every">
                  {show.gap && (gap[i] ?? 0) > 0.05 && badge(top[i].x, (top[i].y + middle[i].y) / 2, gap[i], 'gap', false)}
                  {show.gain && (gain[i] ?? 0) > 0.05 && badge(middle[i].x, (middle[i].y + bottom[i].y) / 2, gain[i], 'gain', false)}
                </g>
              ) : null,
            )}

            {/* Each line is named where it ends, with its last value. */}
            {[[needed, top], [smart, middle], [usual, bottom]].map(([series, line]) => {
              const s = series as typeof needed
              const end = (line as Point[])[last]
              return (
                // In the panel there is room for the value alone; the readout above names the lines. The label
                // stands clear of the line's end, where the cursor's badges sit when the last year is in hand.
                <g key={s.name} className="outlook-end" transform={`translate(${(end.x + (large ? 32 : 22)).toFixed(1)} ${end.y.toFixed(1)})`}>
                  {roomy && <text dy="-0.15em" fontSize={fontSize - 1}>{s.name}</text>}
                  <text className="outlook-end-value" dy={roomy ? '1em' : '0.36em'} fontSize={fontSize + (large ? 5 : 2)}>
                    {one(s.values[last])}
                  </text>
                </g>
              )
            })}

            {/* The year in hand: a line down it, a dot on each series, and the two spaces measured. */}
            <g className="outlook-cursor" style={{ transform: `translateX(${top[at].x.toFixed(1)}px)` }}>
              <line y1={pad.top} y2={height - pad.bottom} />
              {show.gap && <line className="outlook-span outlook-gap" y1={top[at].y} y2={middle[at].y} />}
              {show.gain && <line className="outlook-span outlook-gain" y1={middle[at].y} y2={bottom[at].y} />}
              <circle className="outlook-dot outlook-needed" cy={top[at].y} r={large ? 6.5 : 5} />
              <circle className="outlook-dot outlook-smart" cy={middle[at].y} r={large ? 6.5 : 5} />
              <circle className="outlook-dot outlook-usual" cy={bottom[at].y} r={large ? 6.5 : 5} />
              {show.gap && (gap[at] ?? 0) > 0.05 && badge(0, (top[at].y + middle[at].y) / 2, gap[at], 'gap', true)}
              {show.gain && (gain[at] ?? 0) > 0.05 && badge(0, (middle[at].y + bottom[at].y) / 2, gain[at], 'gain', true)}
            </g>
          </svg>
        )}
      </div>

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
              {spec.series.map((series) => (
                <th key={series.name} scope="col">{series.name}</th>
              ))}
              <th scope="col">Food gap</th>
              <th scope="col">Gain from climate smart agriculture</th>
            </tr>
          </thead>
          <tbody>
            {years.map((value, i) => (
              <tr key={value}>
                <th scope="row">{value}</th>
                {spec.series.map((series) => (
                  <td key={series.name}>{one(series.values[i])}</td>
                ))}
                <td>{one(gap[i])}</td>
                <td>{one(gain[i])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  )
}
