/** Helpers for the crop calendar: a year laid out left to right, January to December. */

export const MONTH_LETTERS = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D']

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const percent = (months: number) => `${+((months / 12) * 100).toFixed(3)}%`
const clamp = (months: number) => Math.min(12, Math.max(0, months))

/** Where a month range sits along the year. Months count from 0 (start of January) to 12 (end of December). */
export function barPosition([start, end]: number[]): { left: string; width: string } {
  const from = clamp(start)
  return { left: percent(from), width: percent(Math.max(0, clamp(end) - from)) }
}

/** How far through its year a date falls, from 0 up to (not including) 1. */
export function yearFraction(date: Date): number {
  const daysInMonth = new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate()
  return (date.getMonth() + (date.getDate() - 1) / daysInMonth) / 12
}

function describeRange([start, end]: number[]): string {
  const from = Number.isInteger(start) ? MONTH_NAMES[start] : `mid ${MONTH_NAMES[Math.floor(start)]}`
  const to = Number.isInteger(end) ? MONTH_NAMES[end - 1] : `mid ${MONTH_NAMES[Math.floor(end)]}`
  return from === to ? from : `${from} to ${to}`
}

/** Month ranges in words: "October to December", "June to mid July". */
export function describeRanges(ranges: number[][]): string {
  return ranges.map(describeRange).join(', and ')
}
