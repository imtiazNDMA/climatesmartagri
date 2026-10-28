import { SLOT_COLOURS } from '../charts/chartOption'
import { utcTime } from './format'

// The portal chart inks (chartOption.ts): on the dark card every text colour reads at 4.5:1 or better.
const INK = {
  light: { ink: '#52514e', grid: '#e1e0d9', surface: '#ffffff' },
  dark: { ink: '#d4dbe6', grid: '#2b3a51', surface: '#18243a' },
}
const FONT = "system-ui, 'Segoe UI', sans-serif"
const FAILED = '#e34948'

function base(dark: boolean) {
  const p = dark ? INK.dark : INK.light
  return {
    animationDuration: 600,
    textStyle: { fontFamily: FONT, color: p.ink, fontSize: 13 },
    grid: { left: 8, right: 16, top: 36, bottom: 8, outerBoundsMode: 'same', outerBoundsContain: 'axisLabel' },
    tooltip: { trigger: 'axis', backgroundColor: p.surface, borderColor: p.grid, textStyle: { color: p.ink } },
    legend: { top: 0, left: 0, textStyle: { color: p.ink } },
    palette: p,
  }
}

/** Pass^k over time, one line per dataset, live runs only. */
export function passRateOption(series: { dataset: string; points: [string, number][] }[], dark: boolean): Record<string, unknown> {
  const { palette, ...common } = base(dark)
  return {
    ...common,
    xAxis: { type: 'time', axisLine: { lineStyle: { color: palette.grid } }, axisLabel: { color: palette.ink } },
    yAxis: {
      type: 'value', min: 0, max: 100, axisLabel: { color: palette.ink, formatter: '{value}%' },
      splitLine: { lineStyle: { color: palette.grid } },
    },
    series: series.map((s, i) => ({
      name: s.dataset,
      type: 'line',
      symbolSize: 8,
      lineStyle: { width: 3, color: SLOT_COLOURS[i % SLOT_COLOURS.length] },
      itemStyle: { color: SLOT_COLOURS[i % SLOT_COLOURS.length] },
      data: s.points.map(([at, rate]) => [at, Math.round(rate * 1000) / 10]),
    })),
  }
}

/** Questions per day, answered and failed stacked. */
export function requestsOption(byDay: { day: string; requests: number; errors: number }[], dark: boolean): Record<string, unknown> {
  const { palette, ...common } = base(dark)
  return {
    ...common,
    xAxis: {
      type: 'category', data: byDay.map((d) => utcTime(`${d.day}T00:00:00+00:00`).split(' ').slice(0, 2).join(' ')),
      axisLabel: { color: palette.ink }, axisLine: { lineStyle: { color: palette.grid } },
    },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { color: palette.ink }, splitLine: { lineStyle: { color: palette.grid } } },
    series: [
      { name: 'Answered', type: 'bar', stack: 'q', itemStyle: { color: SLOT_COLOURS[0] }, data: byDay.map((d) => d.requests - d.errors) },
      { name: 'Failed', type: 'bar', stack: 'q', itemStyle: { color: FAILED }, data: byDay.map((d) => d.errors) },
    ],
  }
}
