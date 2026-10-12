import type { ChartSpec, ChartSeries } from '../api/types'

/** Categorical colours in fixed slot order; a series keeps its slot wherever it appears. */
export const SLOT_COLOURS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948']

const INK = '#52514e'
const STRONG = '#1c1c1a'
const MUTED = '#898781'
const GRID = '#e1e0d9'
const AXIS = '#c3c2b7'
const SURFACE = '#ffffff'
/** The page's font, by name: labels are measured before they are drawn, and 'inherit' measures as another font. */
const FONT = "system-ui, 'Segoe UI', sans-serif"
const DIMMED_BAR = '#b7d3f6'
const SURPLUS = '#2a78d6'
const SHORTFALL = '#eb6834'
/** Text inside a plot: axis names, bar values, line labels and the legend. Larger in the full view. */
const textSize = (large: boolean) => (large ? 17 : 15)
/** How long a chart takes to draw itself in. */
export const DRAW_MS = 1400
/** How often a chart draws itself in again, so the page keeps moving. */
export const REPLAY_MS = 9000
/** Bars are labelled with their value only while there are few enough to read. */
const MAX_LABELLED_BARS = 8

export function formatNumber(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return 'Not reported'
  if (typeof value === 'string') return value
  // Two decimals would turn a small amount into 0, so those keep their first two digits instead.
  if (value !== 0 && Math.abs(value) < 0.1) return value.toLocaleString('en-US', { maximumSignificantDigits: 2 })
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
  series.colour ?? (series.emphasis === 'strong' ? STRONG : SLOT_COLOURS[(series.slot - 1) % SLOT_COLOURS.length])

/** The year a chart over time marks: the chosen year if the chart has it, otherwise its latest. */
export function markedYear(spec: ChartSpec, year: number | null): number | null {
  if (!spec.time || spec.categories.length === 0) return null
  const latest = spec.categories[spec.categories.length - 1]
  const chosen = year !== null && spec.categories.includes(year) ? year : latest
  return typeof chosen === 'number' ? chosen : null
}

/** The least room a plot needs. In the full view it grows past this to fill its card. */
export function chartHeight(spec: ChartSpec, large = false): number {
  if (spec.kind === 'bar' && spec.horizontal) {
    return (large ? 76 : 60) + spec.categories.length * (large ? 38 : 30)
  }
  return large ? 380 : 250
}

const valueAxis = (unit: string, fontSize: number, hidden = false, min?: number, max?: number) => ({
  type: 'value',
  ...(min !== undefined ? { min } : {}),
  ...(max !== undefined ? { max } : {}),
  // With its numbers hidden the axis has nothing to name, and the longest bar may run its full length.
  name: hidden || unit === 'times' || unit === '%' ? '' : unit,
  ...(hidden ? { max: 'dataMax' } : {}),
  nameTextStyle: { color: MUTED, align: 'left', fontSize },
  // On a narrow plot the larger text would run together, so a number that would touch its neighbour is left out.
  axisLabel: { show: !hidden, color: MUTED, fontSize, hideOverlap: true, formatter: (value: number) => spoken(value, unit) },
  splitLine: { show: !hidden, lineStyle: { color: GRID } },
})

const categoryAxis = (categories: (string | number)[], fontSize: number, extra: object = {}, label: object = {}) => ({
  type: 'category',
  data: categories.map(String),
  axisLabel: { color: MUTED, fontSize, ...label },
  axisLine: { lineStyle: { color: AXIS } },
  axisTick: { show: false },
  ...extra,
})

const MIN_LABEL_GAP = 22
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
  const top = spec.axis_max ?? Math.max(0, ...ends, ...(stacked ? [] : spec.series.flatMap((s) => s.values.map((v) => v ?? 0))))
  const bottom = spec.axis_min ?? Math.min(0, ...ends, ...spec.series.flatMap((s) => s.values.map((v) => v ?? 0)))
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

function timeSeries(spec: ChartSpec, year: number | null, endLabels: boolean, height: number, fontSize: number) {
  const stacked = spec.kind === 'stacked-area'
  const marked = markedYear(spec, year)
  const offsets = endLabels ? endLabelOffsets(spec, height) : spec.series.map(() => 0)
  return spec.series.map((series, index) => {
    const colour = colourOf(series)
    const marks: object[] = []
    if (index === 0 && marked !== null) marks.push({ xAxis: spec.categories.indexOf(marked) })
    if (index === 0 && spec.zero_line) marks.push({ yAxis: 0, label: { show: false } })
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
        fontSize: textSize(endLabels),
        distance: 8,
        offset: [0, offsets[index]],
      },
      ...(marks.length
        ? {
            markLine: {
              symbol: 'none',
              silent: true,
              // The year marker stays put while the lines draw in.
              animation: false,
              lineStyle: { color: INK, type: 'dashed', width: 1 },
              label: { formatter: marked !== null ? String(marked) : '', color: INK, fontSize },
              data: marks,
            },
          }
        : {}),
    }
  })
}

function barColour(spec: ChartSpec, series: ChartSeries, index: number, value: number | null): string {
  if (spec.bar_colours?.[index]) return spec.bar_colours[index]
  if (series.colour) return series.colour
  if (spec.colour_by_sign) return (value ?? 0) < 0 ? SHORTFALL : SURPLUS
  if (spec.bar_slots) return SLOT_COLOURS[(spec.bar_slots[index] - 1) % SLOT_COLOURS.length]
  const colour = colourOf(series)
  const highlight = spec.highlight ?? null
  return highlight === null || highlight === index ? colour : DIMMED_BAR
}

/** The widest a bar may grow: a few upright bars are broad columns, not thin sticks. */
function barMaxWidth(spec: ChartSpec, large: boolean): number {
  if (spec.horizontal) return large ? 56 : 18
  return large ? 160 : 64
}

/** What is written at the end of a bar: its value, its note, or both when the bar is one amount. */
export function barLabel(spec: ChartSpec, index: number, value: number | null): string {
  const note = spec.bar_notes?.[index]
  if (note === undefined) return spoken(value, spec.unit)
  return spec.stacked ? note : `${spoken(value, spec.unit)} · ${note}`
}

/** True for a bar that is not one of those the headline is about, when the chart names some. */
function fainter(spec: ChartSpec, index: number): boolean {
  if (spec.highlights) return !spec.highlights.includes(index)
  // Bars in their own colours cannot be dimmed by swapping the colour, so the others fade instead.
  return Boolean(spec.bar_colours) && (spec.highlight ?? null) !== null && spec.highlight !== index
}

function barSeries(spec: ChartSpec, large: boolean) {
  const lastSeries = spec.series.length - 1
  const rounded = spec.horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]
  return spec.series.map((series, seriesIndex) => ({
    name: series.name,
    type: 'bar',
    ...(spec.stacked ? { stack: 'total' } : {}),
    barMaxWidth: barMaxWidth(spec, large),
    barCategoryGap: spec.horizontal ? '35%' : '45%',
    // In a stacked bar only the far end is rounded, so the parts meet squarely.
    itemStyle: { color: colourOf(series), borderRadius: !spec.stacked || seriesIndex === lastSeries ? rounded : 0 },
    label: {
      // A stacked bar is labelled once, at its end; bars with notes are always labelled.
      show: spec.bar_notes
        ? !spec.stacked || seriesIndex === lastSeries
        : spec.categories.length <= MAX_LABELLED_BARS,
      position: spec.horizontal ? 'right' : 'top',
      color: INK,
      fontSize: textSize(large),
      formatter: (params: { value: number | null; dataIndex: number }) => barLabel(spec, params.dataIndex, params.value),
    },
    data: series.values.map((value, i) => ({
      value,
      itemStyle: { color: barColour(spec, series, i, value), opacity: fainter(spec, i) ? 0.45 : 1 },
      // The bars the headline is about are labelled in bold, the rest quietly.
      ...(spec.highlights
        ? { label: spec.highlights.includes(i) ? { color: STRONG, fontWeight: 'bold' } : { color: INK } }
        : {}),
      // A bar below zero hangs down to the axis names, so its label goes at the zero line instead.
      ...(value !== null && value < 0 && !spec.horizontal ? { label: { position: 'top' } } : {}),
    })),
  }))
}

/** Room to the right of horizontal bars for what is written at their ends. */
function labelRoom(spec: ChartSpec, large: boolean): number {
  if (!spec.bar_notes) return large ? 84 : 64
  const last = spec.series[spec.series.length - 1]
  const longest = Math.max(0, ...spec.categories.map((_, i) => barLabel(spec, i, last?.values[i] ?? null).length))
  // Roughly the width of that many characters in bold, plus a little air.
  return Math.round(longest * textSize(large) * 0.6) + 20
}

/** The ECharts option for a chart the backend describes. `large` is the full view. */
export function chartOption(spec: ChartSpec, year: number | null, large = false): Record<string, unknown> {
  const isBar = spec.kind === 'bar'
  const endLabels = large && !isBar && Boolean(spec.end_labels)
  const showLegend = spec.series.length > 1 && !endLabels
  const fontSize = textSize(large)
  // A few named bars always keep their names, wrapped onto a second line when they are long.
  const named = isBar && !spec.time && spec.categories.length <= MAX_LABELLED_BARS
  const categories = categoryAxis(
    spec.categories,
    fontSize,
    isBar ? {} : { boundaryGap: false },
    named && !spec.horizontal ? { interval: 0, width: large ? 170 : 110, overflow: 'break' } : {},
  )
  const values = valueAxis(spec.unit, fontSize, Boolean(spec.hide_axis), spec.axis_min, spec.axis_max)
  const horizontal = isBar && Boolean(spec.horizontal)
  const longestName = Math.max(...spec.series.map((s) => s.name.length))
  return {
    // The drawing-in is slow enough to watch: bars grow one after another, lines run left to right.
    animationDuration: DRAW_MS,
    animationEasing: 'cubicOut',
    animationDelay: isBar ? (index: number) => index * 120 : 0,
    textStyle: { fontFamily: FONT, fontSize },
    grid: {
      left: horizontal ? 16 : 4,
      right: endLabels ? Math.max(140, Math.min(360, 24 + longestName * 9)) : horizontal ? labelRoom(spec, large) : 28,
      top: showLegend ? 48 : 32,
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
      textStyle: { color: INK, fontSize },
    },
    tooltip: {
      textStyle: { fontSize },
      trigger: 'axis',
      axisPointer: { type: isBar ? 'shadow' : 'line' },
      valueFormatter: (value: number | null) =>
        value === null || value === undefined ? 'Not reported' : [formatNumber(value), spec.unit].filter(Boolean).join(' '),
    },
    xAxis: horizontal ? values : categories,
    yAxis: horizontal ? { ...categories, inverse: true } : values,
    series: isBar ? barSeries(spec, large) : timeSeries(spec, year, endLabels, chartHeight(spec, large), fontSize),
  }
}
