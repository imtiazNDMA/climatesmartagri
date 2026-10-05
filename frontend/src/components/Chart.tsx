import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import { init, use, type ECharts } from 'echarts/core'
import { SVGRenderer } from 'echarts/renderers'
import { useEffect, useRef } from 'react'
import type { ChartSpec } from '../api/types'
import { chartHeight, chartOption, formatNumber, markedYear } from '../charts/chartOption'
import { viewStore } from '../state/viewState'

use([LineChart, BarChart, GridComponent, LegendComponent, TooltipComponent, MarkLineComponent, SVGRenderer])

/**
 * One chart: a headline that states the finding, a line on how to read it, then the plot.
 * Hover for values, click a legend entry to hide a series, click a year to select it.
 * `large` is the full view, where lines are labelled at their ends.
 */
export function Chart({ spec, year, large = false }: { spec: ChartSpec; year: number | null; large?: boolean }) {
  const plot = useRef<HTMLDivElement>(null)
  const chart = useRef<ECharts | null>(null)
  const latest = useRef(spec)

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
    chart.current?.setOption(chartOption(spec, year, large), true)
  }, [spec, year, large])

  return (
    <figure className={large ? 'chart chart-large' : 'chart'} aria-label={spec.title}>
      <figcaption>
        <h4>{spec.title}</h4>
        {spec.subtitle && <p className="chart-subtitle">{spec.subtitle}</p>}
      </figcaption>
      <div
        ref={plot}
        className="chart-plot"
        style={{ height: chartHeight(spec, large) }}
        data-marked-year={markedYear(spec, year) ?? undefined}
      />
      {spec.note && <p className="chart-note">{spec.note}</p>}
      <details className="chart-table">
        <summary>Show table</summary>
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
