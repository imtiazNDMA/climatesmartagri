import type { ChartSpec, ChartSeries } from '../api/types'

/** Categorical colours in fixed slot order; a series keeps its slot wherever it appears. */
export const SLOT_COLOURS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948']

const INK = '#52514e'
const MUTED = '#898781'
const GRID = '#e1e0d9'
const AXIS = '#c3c2b7'
const SURFACE = '#ffffff'
const DIMMED_BAR = '#b7d3f6'

export function formatNumber(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return 'Not reported'
  if (typeof value === 'string') return value
  return value.toLocaleString('en-US', { maximumFractionDigits: 2 })
}

const colourOf = (series: ChartSeries) => SLOT_COLOURS[(series.slot - 1) % SLOT_COLOURS.length]

/** The year a chart over time marks: the chosen year if the chart has it, otherwise its latest. */
export function markedYear(spec: ChartSpec, year: number | null): number | null {
  if (!spec.time || spec.categories.length === 0) return null
  const latest = spec.categories[spec.categories.length - 1]
  const chosen = year !== null && spec.categories.includes(year) ? year : latest
  return typeof chosen === 'number' ? chosen : null
}

export function chartHeight(spec: ChartSpec): number {
  return spec.kind === 'bar' && spec.horizontal ? 56 + spec.categories.length * 26 : 220
}

const valueAxis = (unit: string) => ({
  type: 'value',
  name: unit,
  nameTextStyle: { color: MUTED, align: 'left' },
  axisLabel: { color: MUTED, formatter: (value: number) => formatNumber(value) },
  splitLine: { lineStyle: { color: GRID } },
})

const categoryAxis = (categories: (string | number)[], extra: object = {}) => ({
  type: 'category',
  data: categories.map(String),
  axisLabel: { color: MUTED },
  axisLine: { lineStyle: { color: AXIS } },
  axisTick: { show: false },
  ...extra,
})

function timeSeries(spec: ChartSpec, year: number | null) {
  const stacked = spec.kind === 'stacked-area'
  const marked = markedYear(spec, year)
  return spec.series.map((series, index) => {
    const colour = colourOf(series)
    const marks: object[] = []
    if (index === 0 && marked !== null) marks.push({ xAxis: spec.categories.indexOf(marked) })
    if (index === 0 && spec.zero_line) marks.push({ yAxis: 0 })
    return {
      name: series.name,
      type: 'line',
      itemStyle: { color: colour },
      // Stacked bands are separated by a thin line in the surface colour.
      lineStyle: stacked ? { width: 1.5, color: SURFACE } : { width: 2, color: colour },
      ...(stacked ? { stack: 'total', areaStyle: { color: colour, opacity: 0.9 } } : {}),
      symbol: 'circle',
      showSymbol: Boolean(series.points),
      data: series.points
        ? series.values.map((value, i) => ({ value, symbolSize: series.points!.includes(i) ? 8 : 0 }))
        : series.values,
      emphasis: { focus: 'series' },
      ...(marks.length
        ? {
            markLine: {
              symbol: 'none',
              silent: true,
              lineStyle: { color: INK, type: 'dashed', width: 1 },
              label: { formatter: marked !== null ? String(marked) : '', color: INK },
              data: marks,
            },
          }
        : {}),
    }
  })
}

function barSeries(spec: ChartSpec) {
  return spec.series.map((series) => {
    const colour = colourOf(series)
    const highlight = spec.highlight ?? null
    return {
      name: series.name,
      type: 'bar',
      barMaxWidth: 18,
      itemStyle: { color: colour, borderRadius: spec.horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0] },
      label: {
        show: spec.categories.length <= 3,
        position: spec.horizontal ? 'right' : 'top',
        color: INK,
        formatter: (params: { value: number | null }) => formatNumber(params.value),
      },
      data: series.values.map((value, i) => ({
        value,
        itemStyle: { color: highlight === null || highlight === i ? colour : DIMMED_BAR },
      })),
    }
  })
}

/** The ECharts option for a chart the backend describes. */
export function chartOption(spec: ChartSpec, year: number | null): Record<string, unknown> {
  const isBar = spec.kind === 'bar'
  const categories = categoryAxis(spec.categories, isBar ? {} : { boundaryGap: false })
  const values = valueAxis(spec.unit)
  const horizontal = isBar && Boolean(spec.horizontal)
  return {
    animationDuration: 300,
    textStyle: { fontFamily: 'inherit' },
    grid: { left: 4, right: 28, top: spec.series.length > 1 ? 44 : 28, bottom: 4, containLabel: true },
    legend: {
      show: spec.series.length > 1,
      top: 0,
      left: 0,
      icon: 'roundRect',
      itemWidth: 12,
      itemHeight: 12,
      textStyle: { color: INK },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: isBar ? 'shadow' : 'line' },
      valueFormatter: (value: number | null) =>
        value === null || value === undefined ? 'Not reported' : [formatNumber(value), spec.unit].filter(Boolean).join(' '),
    },
    xAxis: horizontal ? values : categories,
    yAxis: horizontal ? { ...categories, inverse: true } : values,
    series: isBar ? barSeries(spec) : timeSeries(spec, year),
  }
}
