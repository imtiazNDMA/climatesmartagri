import type { ChartSpec, ChartSeries } from '../api/types'

/** Categorical colours in fixed slot order; a series keeps its slot wherever it appears. */
export const SLOT_COLOURS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948']

const INK = '#52514e'
const STRONG = '#1c1c1a'
const MUTED = '#898781'
const GRID = '#e1e0d9'
const AXIS = '#c3c2b7'
const SURFACE = '#ffffff'
const DIMMED_BAR = '#b7d3f6'
const SURPLUS = '#2a78d6'
const SHORTFALL = '#eb6834'
/** Bars are labelled with their value only while there are few enough to read. */
const MAX_LABELLED_BARS = 8

export function formatNumber(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return 'Not reported'
  if (typeof value === 'string') return value
  return value.toLocaleString('en-US', { maximumFractionDigits: 2 })
}

/** A value with its unit the way people say it: "2.9×", "53.1%", "16,725,843". */
function spoken(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined) return ''
  if (unit === 'times') return `${formatNumber(value)}×`
  if (unit === '%') return `${formatNumber(value)}%`
  return formatNumber(value)
}

const colourOf = (series: ChartSeries) =>
  series.emphasis === 'strong' ? STRONG : SLOT_COLOURS[(series.slot - 1) % SLOT_COLOURS.length]

/** The year a chart over time marks: the chosen year if the chart has it, otherwise its latest. */
export function markedYear(spec: ChartSpec, year: number | null): number | null {
  if (!spec.time || spec.categories.length === 0) return null
  const latest = spec.categories[spec.categories.length - 1]
  const chosen = year !== null && spec.categories.includes(year) ? year : latest
  return typeof chosen === 'number' ? chosen : null
}

export function chartHeight(spec: ChartSpec, large = false): number {
  if (spec.kind === 'bar' && spec.horizontal) {
    return (large ? 72 : 56) + spec.categories.length * (large ? 34 : 26)
  }
  return large ? 360 : 220
}

const valueAxis = (unit: string) => ({
  type: 'value',
  name: unit === 'times' || unit === '%' ? '' : unit,
  nameTextStyle: { color: MUTED, align: 'left' },
  axisLabel: { color: MUTED, formatter: (value: number) => spoken(value, unit) },
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

const MIN_LABEL_GAP = 16
/** Roughly the part of a chart's height taken by its title row and axis, not the plot. */
const CHART_CHROME = 80

/**
 * How far down to move each line's end label so labels of lines that finish close together
 * do not sit on top of each other. Positive is down, in pixels.
 */
export function endLabelOffsets(spec: ChartSpec, height: number): number[] {
  const stacked = spec.kind === 'stacked-area'
  let running = 0
  const ends = spec.series.map((series) => {
    const last = series.values[series.values.length - 1] ?? 0
    running += last
    return stacked ? running : last
  })
  const top = Math.max(0, ...ends, ...(stacked ? [] : spec.series.flatMap((s) => s.values.map((v) => v ?? 0))))
  const bottom = Math.min(0, ...ends, ...spec.series.flatMap((s) => s.values.map((v) => v ?? 0)))
  const scale = (height - CHART_CHROME) / (top - bottom || 1)
  // Pixel position from the top of the plot, highest line first.
  const order = ends.map((value, index) => ({ index, y: (top - value) * scale })).sort((a, b) => a.y - b.y)
  const offsets = ends.map(() => 0)
  let previous = Number.NEGATIVE_INFINITY
  for (const item of order) {
    const placed = Math.max(item.y, previous + MIN_LABEL_GAP)
    offsets[item.index] = Math.round(placed - item.y)
    previous = placed
  }
  return offsets
}

function timeSeries(spec: ChartSpec, year: number | null, endLabels: boolean, height: number) {
  const stacked = spec.kind === 'stacked-area'
  const marked = markedYear(spec, year)
  const offsets = endLabels ? endLabelOffsets(spec, height) : spec.series.map(() => 0)
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
      lineStyle: stacked
        ? { width: 1.5, color: SURFACE }
        : { width: series.emphasis === 'strong' ? 3.5 : 2, color: colour },
      ...(stacked ? { stack: 'total', areaStyle: { color: colour, opacity: 0.9 } } : {}),
      symbol: 'circle',
      showSymbol: Boolean(series.points),
      data: series.points
        ? series.values.map((value, i) => ({ value, symbolSize: series.points!.includes(i) ? 8 : 0 }))
        : series.values,
      emphasis: { focus: 'series' },
      // The name written where the line ends, so nobody has to match colours to a legend.
      endLabel: {
        show: endLabels,
        formatter: '{a}',
        color: series.emphasis === 'strong' ? STRONG : INK,
        fontWeight: series.emphasis === 'strong' ? 'bold' : 'normal',
        distance: 8,
        offset: [0, offsets[index]],
      },
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

function barColour(spec: ChartSpec, series: ChartSeries, index: number, value: number | null): string {
  if (spec.bar_colours?.[index]) return spec.bar_colours[index]
  if (spec.colour_by_sign) return (value ?? 0) < 0 ? SHORTFALL : SURPLUS
  if (spec.bar_slots) return SLOT_COLOURS[(spec.bar_slots[index] - 1) % SLOT_COLOURS.length]
  const colour = colourOf(series)
  const highlight = spec.highlight ?? null
  return highlight === null || highlight === index ? colour : DIMMED_BAR
}

function barSeries(spec: ChartSpec, large: boolean) {
  return spec.series.map((series) => ({
    name: series.name,
    type: 'bar',
    barMaxWidth: large ? 28 : 18,
    itemStyle: { color: colourOf(series), borderRadius: spec.horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0] },
    label: {
      show: spec.categories.length <= MAX_LABELLED_BARS,
      position: spec.horizontal ? 'right' : 'top',
      color: INK,
      formatter: (params: { value: number | null }) => spoken(params.value, spec.unit),
    },
    data: series.values.map((value, i) => ({
      value,
      itemStyle: {
        color: barColour(spec, series, i, value),
        // Bars in their own colours cannot be dimmed by swapping the colour, so the others fade instead.
        opacity: spec.bar_colours && (spec.highlight ?? null) !== null && spec.highlight !== i ? 0.4 : 1,
      },
      // A bar below zero hangs down to the axis names, so its label goes at the zero line instead.
      ...(value !== null && value < 0 && !spec.horizontal ? { label: { position: 'top' } } : {}),
    })),
  }))
}

/** The ECharts option for a chart the backend describes. `large` is the full view. */
export function chartOption(spec: ChartSpec, year: number | null, large = false): Record<string, unknown> {
  const isBar = spec.kind === 'bar'
  const endLabels = large && !isBar && Boolean(spec.end_labels)
  const showLegend = spec.series.length > 1 && !endLabels
  const categories = categoryAxis(spec.categories, isBar ? {} : { boundaryGap: false })
  const values = valueAxis(spec.unit)
  const horizontal = isBar && Boolean(spec.horizontal)
  const longestName = Math.max(...spec.series.map((s) => s.name.length))
  return {
    animationDuration: 300,
    textStyle: { fontFamily: 'inherit', fontSize: large ? 13 : 12 },
    grid: {
      left: horizontal ? 16 : 4,
      right: endLabels ? Math.max(120, Math.min(300, 24 + longestName * 7)) : horizontal ? 64 : 28,
      top: showLegend ? 44 : 28,
      bottom: 4,
      containLabel: true,
    },
    legend: {
      show: showLegend,
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
    series: isBar ? barSeries(spec, large) : timeSeries(spec, year, endLabels, chartHeight(spec, large)),
  }
}
