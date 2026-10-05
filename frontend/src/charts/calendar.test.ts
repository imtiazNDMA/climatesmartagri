import { describe, expect, it } from 'vitest'
import { barPosition, describeRanges, MONTH_LETTERS, yearFraction } from './calendar'

describe('barPosition', () => {
  it('places a month range along the year as a left edge and a width, in percent', () => {
    expect(barPosition([0, 12])).toEqual({ left: '0%', width: '100%' })
    expect(barPosition([9, 12])).toEqual({ left: '75%', width: '25%' })
    expect(barPosition([5, 6.5])).toEqual({ left: '41.667%', width: '12.5%' })
  })

  it('keeps a range inside the year and never gives a negative width', () => {
    expect(barPosition([-1, 2])).toEqual({ left: '0%', width: '16.667%' })
    expect(barPosition([11, 14])).toEqual({ left: '91.667%', width: '8.333%' })
    expect(barPosition([6, 6])).toEqual({ left: '50%', width: '0%' })
    expect(barPosition([8, 3])).toEqual({ left: '66.667%', width: '0%' })
  })
})

describe('yearFraction', () => {
  it('is how far through the year a date falls', () => {
    expect(yearFraction(new Date(2026, 0, 1))).toBe(0)
    expect(yearFraction(new Date(2026, 6, 1))).toBeCloseTo(0.5, 5)
    expect(yearFraction(new Date(2026, 9, 5))).toBeCloseTo((9 + 4 / 31) / 12, 5)
    expect(yearFraction(new Date(2026, 11, 31))).toBeLessThan(1)
  })
})

describe('describeRanges', () => {
  it('names month ranges in words, for labels and screen readers', () => {
    expect(describeRanges([[9, 12]])).toBe('October to December')
    expect(describeRanges([[5, 6]])).toBe('June')
    expect(describeRanges([[5, 6.5]])).toBe('June to mid July')
    expect(describeRanges([[5.5, 7]])).toBe('mid June to July')
    expect(describeRanges([[1, 3], [8, 10]])).toBe('February to March, and September to October')
    expect(describeRanges([[10, 12], [0, 2]])).toBe('November to December, and January to February')
    expect(describeRanges([])).toBe('')
  })
})

describe('MONTH_LETTERS', () => {
  it('has one letter per month', () => {
    expect(MONTH_LETTERS.join('')).toBe('JFMAMJJASOND')
  })
})
