/** The arithmetic behind the outlook chart: its scale, its lines and bands as SVG paths, and what the pointer is over. */

export interface Point {
  x: number
  y: number
}

/** Round ends and evenly spaced ticks that take in a range of values, aiming at about `target` ticks. */
export function niceScale(min: number, max: number, target = 6): { min: number; max: number; ticks: number[] } {
  if (!(max > min)) return { min: min - 1, max: max + 1, ticks: [min - 1, min, max + 1] }
  const rough = (max - min) / Math.max(1, target - 1)
  const power = 10 ** Math.floor(Math.log10(rough))
  const step = ([1, 2, 2.5, 5, 10].find((m) => m * power >= rough) ?? 10) * power
  const low = Math.floor(min / step) * step
  const high = Math.ceil(max / step) * step
  const ticks: number[] = []
  for (let value = low; value <= high + step / 2; value += step) ticks.push(Number(value.toFixed(6)))
  return { min: low, max: high, ticks }
}

/** A function from a value in one range to a position in another, in a straight line. */
export function linear(fromMin: number, fromMax: number, toMin: number, toMax: number): (value: number) => number {
  const span = fromMax - fromMin || 1
  return (value) => toMin + ((value - fromMin) / span) * (toMax - toMin)
}

const at = (point: Point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`

/** A line through the points, as an SVG path. */
export function linePath(points: Point[]): string {
  return points.map((point, i) => `${i === 0 ? 'M' : 'L'}${at(point)}`).join(' ')
}

/** The area between two lines over the same x positions, as a closed SVG path: along the upper, back along the lower. */
export function bandPath(upper: Point[], lower: Point[]): string {
  if (upper.length === 0) return ''
  return `${linePath(upper)} ${[...lower].reverse().map((point) => `L${at(point)}`).join(' ')} Z`
}

/** The index of the position closest to x. */
export function nearestIndex(positions: number[], x: number): number {
  let best = 0
  for (let i = 1; i < positions.length; i++) {
    if (Math.abs(positions[i] - x) < Math.abs(positions[best] - x)) best = i
  }
  return best
}

/**
 * The years to write along the bottom: the first and last, and the round ones between that are not so close
 * to an end as to run into it.
 */
export function tickYears(years: number[], every = 5, clear = 2): number[] {
  if (years.length === 0) return []
  const [first, last] = [years[0], years[years.length - 1]]
  const round = years.filter((year) => year % every === 0 && year - first >= clear && last - year >= clear)
  return [...new Set([first, ...round, last])]
}

/** One series less another, year by year; null where either is missing. */
export function difference(a: (number | null)[], b: (number | null)[]): (number | null)[] {
  return a.map((value, i) => (value === null || b[i] === null || b[i] === undefined ? null : value - b[i]!))
}
