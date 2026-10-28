import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import { init, use as registerEChartsModules, type ECharts } from 'echarts/core'
import { SVGRenderer } from 'echarts/renderers'
import { Table2 } from 'lucide-react'
import { useEffect, useRef, type ReactNode } from 'react'
import type { ChartSpec } from '../api/types'
import { chartHeight, chartOption, formatNumber, markedYear, REPLAY_MS } from '../charts/chartOption'
import { useDarkTheme } from '../state/useDarkTheme'
import { viewStore } from '../state/viewState'

registerEChartsModules([
  LineChart,
  BarChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  MarkLineComponent,
  SVGRenderer,
])

/**
 * One chart: a headline that states the finding, then the plot.
 * Hover for values, click a legend entry to hide a series, click a year to select it.
 * `large` is the full view, where lines are labelled at their ends.
 * Most charts draw themselves in again periodically. The editorial emissions chart animates once.
 */
export function Chart({
  spec, year, large = false, switcher,
}: { spec: ChartSpec; year: number | null; large?: boolean; switcher?: ReactNode }) {
  const plot = useRef<HTMLDivElement>(null)
  const chart = useRef<ECharts | null>(null)
  const latest = useRef(spec)
  const draw = useRef(() => {})
  const dark = useDarkTheme()
  const isEmissionsTrend = spec.id === 'emissions-by-gas'

  useEffect(() => {
    latest.current = spec
  }, [spec])

  useEffect(() => {
    if (!plot.current) return
    const instance = init(plot.current, undefined, { renderer: 'svg' })
    chart.current = instance
    const resize = new ResizeObserver(() => instance.resize())
    resize.observe(plot.current)
    instance.getZr().on('click', (event) => {
      const current = latest.current
      if (!current.time) return
      const point = instance.convertFromPixel({ seriesIndex: 0 }, [event.offsetX, event.offsetY])
      const picked = current.categories[Math.round(Array.isArray(point) ? point[0] : point)]
      if (typeof picked === 'number') viewStore.getState().setYear(picked)
    })
    return () => {
      resize.disconnect()
      instance.dispose()
      chart.current = null
    }
  }, [spec.id])

  useEffect(() => {
    chart.current?.setOption(chartOption(spec, year, large, dark), true)
    // Emptying the chart first makes it draw in from nothing, as it did when it first appeared.
    draw.current = () => {
      chart.current?.clear()
      chart.current?.setOption(chartOption(spec, year, large, dark), true)
    }
  }, [spec, year, large, dark])

  useEffect(() => {
    const element = plot.current
    if (!element || spec.id === 'emissions-by-gas' || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    let reading = false
    const enter = () => { reading = true }
    const leave = () => { reading = false }
    element.addEventListener('pointerenter', enter)
    element.addEventListener('pointerleave', leave)
    const timer = window.setInterval(() => {
      if (!reading && !document.hidden && !latest.current.still) draw.current()
    }, REPLAY_MS)
    return () => {
      window.clearInterval(timer)
      element.removeEventListener('pointerenter', enter)
      element.removeEventListener('pointerleave', leave)
    }
  }, [spec.id])

  const firstTotal = spec.series.reduce((sum, series) => sum + (series.values[0] ?? 0), 0)
  const lastIndex = spec.categories.length - 1
  const lastTotal = spec.series.reduce((sum, series) => sum + (series.values[lastIndex] ?? 0), 0)
  const growth = firstTotal ? lastTotal / firstTotal : 0
  const growthPercent = firstTotal ? Math.round((lastTotal / firstTotal - 1) * 100) : 0

  return (
    <figure className={`${large ? 'chart chart-large' : 'chart'}${isEmissionsTrend ? ' chart-editorial' : ''}`} aria-label={spec.title}>
      <figcaption>
        {switcher}
        {isEmissionsTrend && <span className="chart-eyebrow">Emissions trend · 1994–2025</span>}
        <h4>{spec.title}</h4>
        {isEmissionsTrend && <p className="chart-subtitle">Total greenhouse gas emissions by gas, 1994–2025 · MtCO₂e</p>}
        {/* Bars without an axis still need their unit said once. */}
        {spec.hide_axis && spec.unit && !spec.bar_labels && <p className="chart-unit">Bar length: {spec.unit}</p>}
      </figcaption>
      {isEmissionsTrend && (
        <div className="chart-editorial-summary" aria-label={`${growth.toFixed(1)} times growth from ${formatNumber(firstTotal)} to ${formatNumber(lastTotal)} megatonnes carbon dioxide equivalent`}>
          <div className="chart-editorial-metric">
            <strong>{growth.toFixed(1)}×</strong>
            <span>growth over 31 years</span>
          </div>
          <div className="chart-editorial-range" aria-hidden="true">
            <span><small>1994</small><b>{formatNumber(firstTotal)}</b></span>
            <i><em>+{growthPercent}%</em></i>
            <span><small>2025</small><b>{formatNumber(lastTotal)} MtCO₂e</b></span>
          </div>
        </div>
      )}
      <div
        ref={plot}
        className="chart-plot"
        // In the full view the plot stretches to fill its card, so the height is only a floor.
        style={large ? { minHeight: chartHeight(spec, large) } : { height: chartHeight(spec, large) }}
        data-marked-year={markedYear(spec, year) ?? undefined}
      />
      {spec.note && <p className="chart-note">{spec.note}</p>}
      <details className="chart-table">
        <summary title="Show table">
          <Table2 size={17} aria-hidden />
          <span>Show table</span>
        </summary>
        <table>
          <thead>
            <tr>
              <th>{spec.time ? 'Year' : ''}</th>
              {spec.series.map((series) => (
                <th key={series.name}>{series.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {spec.categories.map((category, row) => (
              <tr key={category}>
                <th>{category}</th>
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
