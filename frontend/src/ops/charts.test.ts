import { describe, expect, it } from 'vitest'
import { passRateOption, requestsOption } from './charts'

describe('ops charts', () => {
  it('draws one labelled line per dataset on a 0–100% axis', () => {
    const option = passRateOption([
      { dataset: 'golden', points: [['2026-10-14T12:00:00+00:00', 2 / 3], ['2026-10-15T12:00:00+00:00', 0.5]] },
      { dataset: 'adversarial', points: [['2026-10-15T12:00:00+00:00', 1]] },
    ], false) as { series: { name: string; data: [string, number][] }[]; yAxis: { max: number } }

    expect(option.series.map((s) => s.name)).toEqual(['golden', 'adversarial'])
    expect(option.series[0].data[1]).toEqual(['2026-10-15T12:00:00+00:00', 50])
    expect(option.yAxis.max).toBe(100)
  })

  it('stacks answered and failed questions per day', () => {
    const option = requestsOption([{ day: '2026-10-16', requests: 3, errors: 1 }], true) as {
      xAxis: { data: string[] }; series: { name: string; data: number[] }[]
    }

    expect(option.xAxis.data).toEqual(['16 Oct'])
    expect(option.series.map((s) => [s.name, s.data])).toEqual([['Answered', [2]], ['Failed', [1]]])
  })
})
