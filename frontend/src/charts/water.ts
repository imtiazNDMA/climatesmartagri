/**
 * The arithmetic of the water balance at any irrigation efficiency. The source gives the water crops need
 * at three efficiencies, and in it need times efficiency is the same at all three: what the crop must
 * actually receive does not change, only how much has to be supplied to deliver it. So the need at any
 * other efficiency follows from the need at one of them.
 */

/** The water crops need each year at an efficiency, from the need at a base efficiency. */
export function needAt(needAtBase: (number | null)[], base: number, efficiency: number): (number | null)[] {
  return needAtBase.map((need) => (need === null ? null : (need * base) / efficiency))
}

/** Water available less water needed, year by year: above zero is a buffer, below it a deficit. */
export function balanceOf(available: (number | null)[], need: (number | null)[]): (number | null)[] {
  return available.map((water, i) => (water === null || need[i] === null || need[i] === undefined ? null : water - need[i]!))
}

/** The first year the balance is below zero, or null when it never is. */
export function firstDeficitYear(years: number[], balance: (number | null)[]): number | null {
  const at = balance.findIndex((value) => value !== null && value < 0)
  return at < 0 ? null : years[at]
}

/** The efficiency at which need would exactly equal what is available, year by year. */
export function breakEven(needAtBase: (number | null)[], base: number, available: (number | null)[]): (number | null)[] {
  return needAtBase.map((need, i) => (need === null || !available[i] ? null : (need * base) / available[i]!))
}

/** The efficiencies from one to another in even steps, both ends included. */
export function efficiencySteps(min: number, max: number, step: number): number[] {
  const steps: number[] = []
  for (let value = min; value <= max + step / 1000; value += step) steps.push(Number(value.toFixed(4)))
  return steps
}

const hex = (channels: number[]) => `#${channels.map((c) => Math.round(c).toString(16).padStart(2, '0')).join('')}`
const DEFICIT = [200, 55, 40]
const NEUTRAL = [246, 244, 238]
const BUFFER = [28, 132, 84]

/**
 * The colour for a balance: red for a deficit, green for a buffer, deeper the further from zero, and pale
 * at zero. `most` is the balance, either way, at which the colour is at its deepest.
 */
export function balanceColour(balance: number | null, most: number): string {
  if (balance === null) return '#e2e8f0'
  const share = Math.min(1, Math.abs(balance) / (most || 1))
  // A balance just either side of zero must still read as its own colour, so the scale starts part-way in.
  const depth = balance === 0 ? 0 : 0.22 + 0.78 * share
  const end = balance < 0 ? DEFICIT : BUFFER
  return hex(NEUTRAL.map((c, i) => c + (end[i] - c) * depth))
}
