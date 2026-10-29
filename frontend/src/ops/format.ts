const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** A share as a percentage, or a dash when there is none. */
export function percent(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? '–' : `${(value * 100).toFixed(digits)}%`
}

export function seconds(ms: number | null | undefined): string {
  return ms === null || ms === undefined ? '–' : `${(ms / 1000).toFixed(1)} s`
}

/** "16 Oct 09:05 UTC": every reader of the dashboard sees the same time. */
export function utcTime(iso: string): string {
  const at = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${at.getUTCDate()} ${MONTHS[at.getUTCMonth()]} ${pad(at.getUTCHours())}:${pad(at.getUTCMinutes())} UTC`
}

export function plural(count: number, word: string, many = `${word}s`): string {
  return `${count} ${count === 1 ? word : many}`
}
