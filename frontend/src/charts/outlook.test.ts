import { describe, expect, it } from 'vitest'
import { bandPath, difference, linePath, linear, nearestIndex, niceScale, tickYears } from './outlook'

describe('niceScale', () => {
  it('takes in the values with round ends and even ticks', () => {
    expect(niceScale(68.2, 168.7)).toEqual({ min: 50, max: 175, ticks: [50, 75, 100, 125, 150, 175] })
    expect(niceScale(68.2, 168.7, 8)).toEqual({ min: 60, max: 180, ticks: [60, 80, 100, 120, 140, 160, 180] })
    expect(niceScale(0, 1)).toEqual({ min: 0, max: 1, ticks: [0, 0.2, 0.4, 0.6, 0.8, 1] })
  })

  it('still gives a scale when every value is the same', () => {
    const scale = niceScale(5, 5)
    expect(scale.min).toBeLessThan(5)
    expect(scale.max).toBeGreaterThan(5)
  })
})

describe('linear', () => {
  it('maps one range onto another, upside down too', () => {
    const y = linear(60, 180, 300, 0)
    expect(y(60)).toBe(300)
    expect(y(180)).toBe(0)
    expect(y(120)).toBe(150)
  })
})

describe('paths', () => {
  const upper = [{ x: 0, y: 10 }, { x: 50, y: 5 }]
  const lower = [{ x: 0, y: 20 }, { x: 50, y: 30 }]

  it('draws a line through its points', () => {
    expect(linePath(upper)).toBe('M0.0,10.0 L50.0,5.0')
  })

  it('closes a band along the upper line and back along the lower', () => {
    expect(bandPath(upper, lower)).toBe('M0.0,10.0 L50.0,5.0 L50.0,30.0 L0.0,20.0 Z')
    expect(bandPath([], [])).toBe('')
  })
})

describe('pointing', () => {
  it('finds the position closest to the pointer', () => {
    expect(nearestIndex([0, 10, 20, 30], 14)).toBe(1)
    expect(nearestIndex([0, 10, 20, 30], 16)).toBe(2)
    expect(nearestIndex([0, 10, 20, 30], -50)).toBe(0)
    expect(nearestIndex([0, 10, 20, 30], 500)).toBe(3)
  })
})

describe('tickYears', () => {
  it('writes the ends and the round years between, leaving out one that would run into an end', () => {
    const years = Array.from({ length: 22 }, (_, i) => 2026 + i)
    expect(tickYears(years)).toEqual([2026, 2030, 2035, 2040, 2045, 2047])
    expect(tickYears([2029, 2030, 2031, 2032, 2033, 2034, 2035, 2036])).toEqual([2029, 2036])
    expect(tickYears([])).toEqual([])
  })
})

describe('difference', () => {
  it('takes one series from another year by year, and has nothing where either has nothing', () => {
    expect(difference([10, 20, null, 40], [1, null, 3, 4])).toEqual([9, null, null, 36])
  })
})
