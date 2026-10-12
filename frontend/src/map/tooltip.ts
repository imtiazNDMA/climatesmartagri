/** Why a word is picked out: a pay-off, a drawback, or a condition the method depends on. */
export type Tone = 'benefit' | 'caution' | 'condition'
const TONES: readonly string[] = ['benefit', 'caution', 'condition']

/** A stretch of text, picked out in a tone's colour when it has one. */
export interface TooltipPart {
  text: string
  tone?: Tone
}

/** One thing said about a row: plain text, or text under a short label such as "Suits". */
export interface TooltipPoint {
  label?: string
  /** The colour of the label, and what kind of statement this is. */
  tone?: Tone
  text: string
  /** The same text cut where its highlighted words begin and end. */
  parts?: TooltipPart[]
}

export interface TooltipRow {
  /** A picture for the row, by name; rows with a name the page does not know go without. */
  icon?: string
  name: string
  points: TooltipPoint[]
}

/** A small two-column table a shape can carry for its popup: what each row is, then what is said about it. */
export interface TooltipTable {
  title?: string
  columns: [string, string]
  rows: TooltipRow[]
}

const isText = (value: unknown): value is string => typeof value === 'string'
const tone = (value: unknown): Tone | undefined => (isText(value) && TONES.includes(value) ? (value as Tone) : undefined)

function parts(value: unknown, whole: string): TooltipPart[] | undefined {
  if (!Array.isArray(value)) return undefined
  const read: TooltipPart[] = []
  for (const item of value) {
    if (typeof item !== 'object' || item === null || !isText((item as TooltipPart).text)) return undefined
    const picked = tone((item as TooltipPart).tone)
    read.push(picked ? { text: (item as TooltipPart).text, tone: picked } : { text: (item as TooltipPart).text })
  }
  // Highlights only decorate the sentence; parts that do not add up to it are dropped, not shown.
  return read.map((part) => part.text).join('') === whole ? read : undefined
}

function point(value: unknown): TooltipPoint | null {
  if (typeof value !== 'object' || value === null) return null
  const raw = value as Record<string, unknown>
  if (!isText(raw.text)) return null
  const read: TooltipPoint = { text: raw.text }
  if (isText(raw.label) && raw.label !== '') read.label = raw.label
  const picked = tone(raw.tone)
  if (picked) read.tone = picked
  const cut = parts(raw.parts, raw.text)
  if (cut) read.parts = cut
  return read
}

function row(value: unknown): TooltipRow | null {
  if (typeof value !== 'object' || value === null) return null
  const { icon, name, points } = value as Record<string, unknown>
  if (!isText(name) || !Array.isArray(points) || points.length === 0) return null
  const read = points.map(point)
  if (read.some((p) => p === null)) return null
  return { ...(isText(icon) ? { icon } : {}), name, points: read as TooltipPoint[] }
}

/**
 * The table in a clicked shape's properties, or null when it has none or it is not well formed.
 * The map hands nested properties back as JSON text, so both forms are accepted.
 */
export function tooltipTable(properties: Record<string, unknown> | null | undefined): TooltipTable | null {
  let table: unknown = properties?.table
  if (isText(table)) {
    try {
      table = JSON.parse(table)
    } catch {
      return null
    }
  }
  if (typeof table !== 'object' || table === null) return null
  const { title, columns, rows } = table as Record<string, unknown>
  if (!Array.isArray(columns) || columns.length !== 2 || !columns.every(isText)) return null
  if (!Array.isArray(rows) || rows.length === 0) return null
  const read = rows.map(row)
  if (read.some((r) => r === null)) return null
  return {
    ...(isText(title) ? { title } : {}),
    columns: columns as [string, string],
    rows: read as TooltipRow[],
  }
}

/**
 * A one-line label split into what is measured and its value, at the first colon:
 * "Surface water irrigation: 0.34 million acres" gives the name and "0.34 million acres".
 * A sentence without one stays whole.
 */
export function labelParts(label: string): { name: string | null; value: string } {
  const at = label.indexOf(': ')
  return at < 0 ? { name: null, value: label } : { name: label.slice(0, at), value: label.slice(at + 2) }
}

/**
 * A value that opens with a number, as the number and what follows it, so the number can count up:
 * "1.66 million acres" gives 1.66, two decimals, and " million acres". Null when the value does not start
 * with a number.
 */
export function leadingNumber(value: string): { number: number; decimals: number; rest: string } | null {
  const match = /^-?\d[\d,]*(\.\d+)?/.exec(value)
  if (!match) return null
  const number = Number(match[0].replaceAll(',', ''))
  if (!Number.isFinite(number)) return null
  return { number, decimals: match[1] ? match[1].length - 1 : 0, rest: value.slice(match[0].length) }
}
