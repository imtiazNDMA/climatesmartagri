import { describe, expect, it } from 'vitest'
import type { ChartSpec } from '../api/types'
import {
  barLabel, chartHeight, chartOption, endLabelOffsets, formatNumber, markedYear, SLOT_COLOURS,
} from './chartOption'

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
const option = (spec: ChartSpec, year: number | null = null, large = false) =>
  chartOption(spec, year, large) as Loose

describe('formatNumber', () => {
  it('groups thousands and trims decimals', () => {
    expect(formatNumber(16725843)).toBe('16,725,843')
    expect(formatNumber(521.456)).toBe('521.46')
    expect(formatNumber(-23.9)).toBe('-23.9')
    expect(formatNumber(80)).toBe('80')
  })
  it('keeps the first two digits of a small amount instead of rounding it to nothing', () => {
    expect(formatNumber(0.0012355)).toBe('0.0012')
    expect(formatNumber(0.0478)).toBe('0.048')
    expect(formatNumber(0.25)).toBe('0.25')
    expect(formatNumber(0)).toBe('0')
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
    expect(o.series[0].markLine.data).toEqual([{ xAxis: 1 }, { yAxis: 0, label: { show: false } }])
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
    expect(chartHeight(lines)).toBe(250)
    expect(chartHeight(lines, true)).toBeGreaterThan(300)
    expect(chartHeight(bars)).toBeLessThan(chartHeight({ ...bars, categories: Array(15).fill('x') }))
  })
})

describe('storytelling styles', () => {
  const story: ChartSpec = {
    ...lines, end_labels: true,
    series: [
      { name: 'Need', slot: 1, values: [1, 2, 3], emphasis: 'strong' },
      { name: 'Supply', slot: 3, values: [3, 2, 1] },
    ],
  }

  it('draws the emphasised series darker and thicker than the others', () => {
    const [strong, plain] = option(story).series
    expect(strong.lineStyle.width).toBeGreaterThan(plain.lineStyle.width)
    expect(strong.itemStyle.color).not.toBe(SLOT_COLOURS[0])
    expect(plain.itemStyle.color).toBe(SLOT_COLOURS[2])
  })

  it('labels the line ends, and drops the legend, only in the large view', () => {
    const large = option(story, null, true)
    expect(large.series.every((s: Loose) => s.endLabel.show === true)).toBe(true)
    expect(large.legend.show).toBe(false)
    expect(large.grid.right).toBeGreaterThan(100)
    const small = option(story)
    expect(small.series.every((s: Loose) => !s.endLabel?.show)).toBe(true)
    expect(small.legend.show).toBe(true)
  })

  it('keeps the legend in the large view when the chart has no end labels', () => {
    expect(option(lines, null, true).legend.show).toBe(true)
  })

  it('colours bars by their own slot when the chart lists them', () => {
    const o = option({ ...bars, highlight: null, bar_slots: [1, 2, 3] })
    expect(o.series[0].data.map((d: Loose) => d.itemStyle.color)).toEqual(SLOT_COLOURS.slice(0, 3))
  })

  it('colours bars by sign when asked: one colour for a shortfall, another for a surplus', () => {
    const o = option({ ...bars, highlight: null, horizontal: false, colour_by_sign: true,
      series: [{ name: 'Balance', slot: 1, values: [-5, 0, 7] }] })
    const colours = o.series[0].data.map((d: Loose) => d.itemStyle.color)
    expect(colours[0]).not.toBe(colours[2])
    expect(colours[1]).toBe(colours[2])
  })

  it('writes bar values the way people say them', () => {
    const label = (unit: string, value: number | null) =>
      option({ ...bars, unit }).series[0].label.formatter({ value })
    expect(label('times', 2.9)).toBe('2.9×')
    expect(label('%', 53.1)).toBe('53.1%')
    expect(label('ha', 16725843)).toBe('16,725,843')
    expect(label('ha', null)).toBe('')
  })

  it('lets a few upright bars grow into broad columns, and more so in the large view', () => {
    const upright = { ...bars, horizontal: false }
    expect(option(upright).series[0].barMaxWidth).toBeGreaterThan(option(bars).series[0].barMaxWidth)
    expect(option(upright, null, true).series[0].barMaxWidth).toBeGreaterThan(option(upright).series[0].barMaxWidth)
  })

  it('writes axis and bar labels larger in the large view', () => {
    const large = option(bars, null, true)
    expect(large.xAxis.axisLabel.fontSize).toBeGreaterThan(option(bars).xAxis.axisLabel.fontSize)
    expect(large.series[0].label.fontSize).toBe(large.yAxis.axisLabel.fontSize)
  })

  it('labels every bar when there are few, and none when there are many', () => {
    expect(option(bars).series[0].label.show).toBe(true)
    expect(option({ ...bars, categories: Array(15).fill('x') }).series[0].label.show).toBe(false)
  })
})

describe('labels that would collide', () => {
  const close: ChartSpec = {
    ...lines, end_labels: true,
    series: [
      { name: 'Available', slot: 1, values: [100, 100, 108] },
      { name: 'Needed at 50%', slot: 3, values: [90, 95, 103] },
      { name: 'Needed at 70%', slot: 4, values: [60, 62, 73] },
    ],
  }

  it('pushes apart end labels of lines that finish close together, and leaves the rest alone', () => {
    const offsets = endLabelOffsets(close, 360)
    expect(offsets[0]).toBe(0)
    expect(offsets[1]).toBeGreaterThan(0)
    expect(offsets[2]).toBe(0)
    // 108 and 103 on a 0-108 axis are about 13px apart on a 280px plot; after the push they are 22.
    expect(offsets[1]).toBeGreaterThanOrEqual(2)
    expect(offsets[1]).toBeLessThan(22)
  })

  it('keeps pushing down a run of three close lines so none overlap', () => {
    const three: ChartSpec = { ...close, series: close.series.map((s, i) => ({ ...s, values: [1, 2, 100 - i] })) }
    const offsets = endLabelOffsets(three, 360)
    expect(offsets[1] - offsets[0]).toBeGreaterThan(10)
    expect(offsets[2] - offsets[1]).toBeGreaterThan(10)
  })

  it('uses the stacked height for a stacked chart', () => {
    const stackedClose: ChartSpec = { ...close, kind: 'stacked-area' }
    // Stacked, the bands end at 108, 211 and 284: far apart, so nothing moves.
    expect(endLabelOffsets(stackedClose, 360)).toEqual([0, 0, 0])
  })

  it('applies the offsets to the end labels in the large view', () => {
    const series = option(close, null, true).series
    expect(series[1].endLabel.offset[1]).toBeGreaterThan(0)
    expect(series[0].endLabel.offset).toEqual([0, 0])
  })

  it('puts the label of a bar below zero at the zero line, clear of the axis names', () => {
    const o = option({ ...bars, highlight: null, horizontal: false, colour_by_sign: true,
      series: [{ name: 'Balance', slot: 1, values: [-5, 3, 7] }] })
    expect(o.series[0].data[0].label.position).toBe('top')
    expect(o.series[0].data[1].label).toBeUndefined()
  })

  it('leaves room on the left for the names of horizontal bars', () => {
    expect(option(bars).grid.left).toBeGreaterThanOrEqual(12)
  })
})

describe('bars in the colours of their map layers', () => {
  const cover: ChartSpec = { ...bars, highlight: null, bar_colours: ['#2e7d32', '#2a78d6', '#eda100'] }

  it('uses the colours the chart lists, one per bar', () => {
    expect(option(cover).series[0].data.map((d: Loose) => d.itemStyle.color)).toEqual(['#2e7d32', '#2a78d6', '#eda100'])
  })

  it('fades the bars that are not highlighted, keeping their colour', () => {
    const data = option({ ...cover, highlight: 1 }).series[0].data
    expect(data.map((d: Loose) => d.itemStyle.color)).toEqual(['#2e7d32', '#2a78d6', '#eda100'])
    expect(data[1].itemStyle.opacity).toBe(1)
    expect(data[0].itemStyle.opacity).toBeLessThan(0.6)
    expect(data[2].itemStyle.opacity).toBeLessThan(0.6)
  })
})

describe('bars that tell a story', () => {
  const split: ChartSpec = {
    id: 'split', title: 'Split', kind: 'bar', unit: 'million acres', time: false, horizontal: true,
    stacked: true, hide_axis: true, still: true, highlights: [1],
    categories: ['Punjab', 'Balochistan'],
    bar_notes: ['14% rainfed', '63% rainfed'],
    series: [
      { name: 'Irrigated cropland', slot: 1, values: [29.3, 1.9], colour: '#2a78d6' },
      { name: 'Rainfed cropland', slot: 4, values: [4.8, 3.2], colour: '#eda100' },
    ],
  }
  const held: ChartSpec = {
    ...split, id: 'held', stacked: false, bar_notes: ['18% of its land', '7% of its land'], highlights: [0],
    series: [{ name: 'Forest', slot: 1, values: [4.48, 3.41] }], bar_colours: ['#2e7d32', '#2e7d32'],
  }

  it('lays stacked series end to end in their own colours, and labels each bar once, at its end', () => {
    const [irrigated, rainfed] = option(split, null, true).series
    expect(irrigated.stack).toBe('total')
    expect(rainfed.stack).toBe('total')
    expect(irrigated.data[0].itemStyle.color).toBe('#2a78d6')
    expect(rainfed.data[0].itemStyle.color).toBe('#eda100')
    expect(irrigated.label.show).toBe(false)
    expect(rainfed.label.show).toBe(true)
    expect(rainfed.label.formatter({ value: 3.2, dataIndex: 1 })).toBe('63% rainfed')
  })

  it('writes the value and the note at the end of a bar that is one amount', () => {
    expect(barLabel(held, 0, 4.48)).toBe('4.48 · 18% of its land')
    expect(barLabel(bars, 0, 30)).toBe('30')
  })

  it('draws the bars the headline is about at full strength and bold, and the rest fainter', () => {
    const rainfed = option(split, null, true).series[1]
    expect(rainfed.data[1].itemStyle.opacity).toBe(1)
    expect(rainfed.data[0].itemStyle.opacity).toBeLessThan(1)
    expect(rainfed.data[1].label.fontWeight).toBe('bold')
    expect(rainfed.data[0].label.fontWeight).toBeUndefined()
  })

  it('leaves the numbers off the value axis and makes room for the words at the bar ends', () => {
    const o = option(held, null, true)
    expect(o.xAxis.axisLabel.show).toBe(false)
    expect(o.xAxis.splitLine.show).toBe(false)
    // The unit is said under the headline instead, and the longest bar runs the full width.
    expect(o.xAxis.name).toBe('')
    expect(o.xAxis.max).toBe('dataMax')
    expect(o.grid.right).toBeGreaterThan(option(bars, null, true).grid.right)
    expect(option(bars, null, true).xAxis.axisLabel.show).toBe(true)
  })
})

describe('a value axis that does not start at zero', () => {
  it('starts and ends where the chart says, and is left alone otherwise', () => {
    const o = option({ ...lines, axis_min: 30, axis_max: 75 })
    expect([o.yAxis.min, o.yAxis.max]).toEqual([30, 75])
    expect(option(lines).yAxis.min).toBeUndefined()
  })
})
