import { describe, expect, it } from 'vitest'
import type { ChartSpec } from '../api/types'
import { chartHeight, chartOption, formatNumber, markedYear, SLOT_COLOURS } from './chartOption'

const lines: ChartSpec = {
  id: 'lines', title: 'Lines', kind: 'line', unit: 'Mt', time: true,
  categories: [2000, 2001, 2002],
  series: [
    { name: 'A', slot: 1, values: [1, 2, 3] },
    { name: 'B', slot: 3, values: [3, 2, 1] },
  ],
}
const stacked: ChartSpec = { ...lines, id: 'stacked', kind: 'stacked-area' }
const single: ChartSpec = {
  ...lines, id: 'single', series: [{ name: 'Total', slot: 1, values: [1, 2, 3], points: [0, 2] }],
}
const bars: ChartSpec = {
  id: 'bars', title: 'Bars', kind: 'bar', unit: 'ha', time: false, horizontal: true, highlight: 1,
  categories: ['Sindh', 'Punjab', 'KP'],
  series: [{ name: 'Area', slot: 1, values: [30, 20, 10] }],
}

// The option is a plain object; these helpers keep the assertions readable.
type Loose = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any
const option = (spec: ChartSpec, year: number | null = null) => chartOption(spec, year) as Loose

describe('formatNumber', () => {
  it('groups thousands and trims decimals', () => {
    expect(formatNumber(16725843)).toBe('16,725,843')
    expect(formatNumber(521.456)).toBe('521.46')
    expect(formatNumber(-23.9)).toBe('-23.9')
    expect(formatNumber(80)).toBe('80')
  })
  it('passes text through and names a missing value', () => {
    expect(formatNumber('PK')).toBe('PK')
    expect(formatNumber(null)).toBe('Not reported')
  })
})

describe('markedYear', () => {
  it('is the chosen year when the chart has it, otherwise the latest', () => {
    expect(markedYear(lines, 2001)).toBe(2001)
    expect(markedYear(lines, null)).toBe(2002)
    expect(markedYear(lines, 1990)).toBe(2002)
  })
  it('is null for a chart that is not over time', () => {
    expect(markedYear(bars, 2001)).toBeNull()
  })
})

describe('chartOption for charts over time', () => {
  it('draws one line per series in its slot colour', () => {
    const o = option(lines)
    expect(o.series.map((s: Loose) => [s.name, s.type, s.itemStyle.color])).toEqual([
      ['A', 'line', SLOT_COLOURS[0]],
      ['B', 'line', SLOT_COLOURS[2]],
    ])
    expect(o.series[0].stack).toBeUndefined()
    expect(o.xAxis.data).toEqual(['2000', '2001', '2002'])
  })

  it('stacks areas for a stacked-area chart', () => {
    const o = option(stacked)
    expect(o.series.every((s: Loose) => s.stack === 'total' && s.areaStyle)).toBe(true)
  })

  it('shows a legend only when there is more than one series', () => {
    expect(option(lines).legend.show).toBe(true)
    expect(option(single).legend.show).toBe(false)
  })

  it('marks the chosen year on the first series, defaulting to the latest', () => {
    expect(option(lines, 2001).series[0].markLine.data).toEqual([{ xAxis: 1 }])
    expect(option(lines, 2001).series[0].markLine.label.formatter).toBe('2001')
    expect(option(lines).series[0].markLine.data).toEqual([{ xAxis: 2 }])
    expect(option(lines, 2001).series[1].markLine).toBeUndefined()
  })

  it('adds a zero line when asked', () => {
    const o = option({ ...lines, zero_line: true }, 2001)
    expect(o.series[0].markLine.data).toEqual([{ xAxis: 1 }, { yAxis: 0 }])
  })

  it('shows dots only at the listed points', () => {
    const data = option(single).series[0].data
    expect(data.map((d: Loose) => d.symbolSize)).toEqual([8, 0, 8])
    expect(data.map((d: Loose) => d.value)).toEqual([1, 2, 3])
  })

  it('formats tooltip values with the unit', () => {
    expect(option(lines).tooltip.valueFormatter(1234.5)).toBe('1,234.5 Mt')
    expect(option({ ...lines, unit: '' }).tooltip.valueFormatter(2)).toBe('2')
    expect(option(lines).tooltip.valueFormatter(null)).toBe('Not reported')
  })
})

describe('chartOption for bar charts', () => {
  it('puts categories on the vertical axis when horizontal, first on top', () => {
    const o = option(bars)
    expect(o.yAxis.type).toBe('category')
    expect(o.yAxis.data).toEqual(['Sindh', 'Punjab', 'KP'])
    expect(o.yAxis.inverse).toBe(true)
    expect(o.xAxis.type).toBe('value')
  })

  it('puts categories on the horizontal axis otherwise', () => {
    const o = option({ ...bars, horizontal: false })
    expect(o.xAxis.type).toBe('category')
    expect(o.yAxis.type).toBe('value')
  })

  it('draws the highlighted bar in full colour and the rest lighter', () => {
    const colours = option(bars).series[0].data.map((d: Loose) => d.itemStyle.color)
    expect(colours[1]).toBe(SLOT_COLOURS[0])
    expect(colours[0]).toBe(colours[2])
    expect(colours[0]).not.toBe(SLOT_COLOURS[0])
  })

  it('draws every bar in full colour when nothing is highlighted', () => {
    const colours = option({ ...bars, highlight: null }).series[0].data.map((d: Loose) => d.itemStyle.color)
    expect(new Set(colours)).toEqual(new Set([SLOT_COLOURS[0]]))
  })

  it('has no year marker', () => {
    expect(option(bars, 2001).series[0].markLine).toBeUndefined()
  })
})

describe('chartHeight', () => {
  it('grows with the number of horizontal bars and is fixed otherwise', () => {
    expect(chartHeight(lines)).toBe(220)
    expect(chartHeight(bars)).toBeLessThan(chartHeight({ ...bars, categories: Array(15).fill('x') }))
  })
})
