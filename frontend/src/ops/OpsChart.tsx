import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { init, use as registerEChartsModules, type ECharts } from 'echarts/core'
import { SVGRenderer } from 'echarts/renderers'
import { useEffect, useRef } from 'react'

registerEChartsModules([LineChart, BarChart, GridComponent, LegendComponent, TooltipComponent, SVGRenderer])

/** One ECharts plot. `label` names it for screen readers; the headline above it states the finding. */
export function OpsChart({ option, label, height = 260 }: { option: Record<string, unknown>; label: string; height?: number }) {
  const plot = useRef<HTMLDivElement>(null)
  const chart = useRef<ECharts | null>(null)

  useEffect(() => {
    if (!plot.current) return
    const instance = init(plot.current, undefined, { renderer: 'svg' })
    chart.current = instance
    const resize = new ResizeObserver(() => instance.resize())
    resize.observe(plot.current)
    return () => {
      resize.disconnect()
      instance.dispose()
      chart.current = null
    }
  }, [])

  useEffect(() => {
    chart.current?.setOption(option, true)
  }, [option])

  return <div ref={plot} className="ops-chart" role="img" aria-label={label} style={{ height }} />
}
