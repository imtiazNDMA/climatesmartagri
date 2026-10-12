import { describe, expect, it } from 'vitest'
import { balanceColour, balanceOf, breakEven, efficiencySteps, firstDeficitYear, needAt } from './water'

// The source's own first and last years: need at 35% efficiency, and water available.
const need35 = [132, 146.6]
const available = [109, 107.9]

describe('needAt', () => {
  it('gives back the source’s own figures at the efficiencies it lists', () => {
    expect(needAt(need35, 35, 35)).toEqual([132, 146.6])
    expect(needAt(need35, 35, 50)[0]).toBeCloseTo(92.4, 6)
    expect(needAt(need35, 35, 70)[0]).toBeCloseTo(66, 6)
    expect(needAt(need35, 35, 70)[1]).toBeCloseTo(73.3, 6)
  })

  it('has nothing for a year the source has nothing for', () => {
    expect(needAt([132, null], 35, 50)[1]).toBeNull()
  })
})

describe('the balance', () => {
  it('is what is available less what is needed', () => {
    const balance = balanceOf(available, needAt(need35, 35, 45))
    expect(balance[0]).toBeCloseTo(6.33, 2) // enough in the first year
    expect(balance[1]).toBeCloseTo(-6.12, 2) // short in the last
    expect(balanceOf([109, null], [100, 100])).toEqual([9, null])
  })

  it('finds the first year of deficit, or none', () => {
    const years = [2026, 2027, 2028]
    expect(firstDeficitYear(years, [5, -1, -3])).toBe(2027)
    expect(firstDeficitYear(years, [5, 0, 3])).toBeNull()
    expect(firstDeficitYear(years, [null, -2, 3])).toBe(2027)
  })
})

describe('breakEven', () => {
  it('is the efficiency at which need would equal what is available', () => {
    const [first, last] = breakEven(need35, 35, available)
    expect(first).toBeCloseTo(42.39, 2)
    expect(last).toBeCloseTo(47.55, 2)
    // At that efficiency the balance is nothing.
    expect(balanceOf([109], needAt([132], 35, first!))[0]).toBeCloseTo(0, 9)
  })
})

describe('efficiencySteps', () => {
  it('runs from one end to the other, both included', () => {
    expect(efficiencySteps(35, 70, 5)).toEqual([35, 40, 45, 50, 55, 60, 65, 70])
    expect(efficiencySteps(35, 40, 2.5)).toEqual([35, 37.5, 40])
  })
})

describe('balanceColour', () => {
  const channels = (colour: string) => [1, 3, 5].map((at) => parseInt(colour.slice(at, at + 2), 16))

  it('is red for a deficit and green for a buffer, deeper the further from zero', () => {
    const [slight, deep] = [channels(balanceColour(-2, 40)), channels(balanceColour(-40, 40))]
    expect(slight[0]).toBeGreaterThan(slight[1]) // red leads
    expect(deep[1]).toBeLessThan(slight[1]) // and deepens
    const buffer = channels(balanceColour(30, 40))
    expect(buffer[1]).toBeGreaterThan(buffer[0]) // green leads
  })

  it('goes no deeper past the most, is pale at zero, and grey where there is no figure', () => {
    expect(balanceColour(-400, 40)).toBe(balanceColour(-40, 40))
    expect(balanceColour(0, 40)).toBe('#f6f4ee')
    expect(balanceColour(null, 40)).toBe('#e2e8f0')
    expect(balanceColour(-0.1, 40)).not.toBe(balanceColour(0.1, 40))
  })
})
