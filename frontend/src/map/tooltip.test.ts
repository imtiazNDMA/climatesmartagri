import { describe, expect, it } from 'vitest'
import { labelParts, leadingNumber, tooltipTable } from './tooltip'

const table = {
  title: 'Bagh tehsil',
  columns: ['Irrigation type', 'Why'],
  rows: [{ icon: 'drip', name: 'Drip irrigation', points: [{ text: 'Feeds the roots.' }, { label: 'Suits', text: 'Orchards.' }] }],
}

describe('tooltipTable', () => {
  it('reads a table whether the map hands it back as an object or as JSON text', () => {
    expect(tooltipTable({ table })).toEqual(table)
    expect(tooltipTable({ table: JSON.stringify(table) })).toEqual(table)
  })

  it('is null when the shape has no table', () => {
    expect(tooltipTable({ label: 'Kind: A' })).toBeNull()
    expect(tooltipTable(null)).toBeNull()
  })

  it('is null for a table that is broken, empty or malformed, so the plain label is used instead', () => {
    expect(tooltipTable({ table: '{not json' })).toBeNull()
    expect(tooltipTable({ table: { ...table, rows: [] } })).toBeNull()
    expect(tooltipTable({ table: { ...table, columns: ['Only one'] } })).toBeNull()
    expect(tooltipTable({ table: { ...table, rows: [{ name: 'Drip', points: [] }] } })).toBeNull()
    expect(tooltipTable({ table: { ...table, rows: [{ name: 'Drip', points: [{ label: 'Suits' }] }] } })).toBeNull()
  })

  it('does without a title, an icon or a label', () => {
    const bare = tooltipTable({ table: { columns: table.columns, rows: [{ name: 'Drip', points: [{ text: 'x' }] }] } })
    expect(bare).toEqual({ columns: table.columns, rows: [{ name: 'Drip', points: [{ text: 'x' }] }] })
  })
})

describe('highlighted words', () => {
  const marked = (parts: unknown, tone?: unknown) =>
    tooltipTable({
      table: { columns: table.columns, rows: [{ name: 'Drip', points: [{ label: 'Helps by', tone, text: 'It saves water.', parts }] }] },
    })?.rows[0].points[0]

  it('keeps the tone of a label and of each highlighted stretch', () => {
    const parts = [{ text: 'It ' }, { text: 'saves water', tone: 'benefit' }, { text: '.' }]
    expect(marked(parts, 'benefit')).toEqual({ label: 'Helps by', tone: 'benefit', text: 'It saves water.', parts })
  })

  it('drops a tone it does not know, and highlights that do not add up to the sentence', () => {
    expect(marked([{ text: 'It saves water.', tone: 'shouting' }], 'shouting')).toEqual({
      label: 'Helps by', text: 'It saves water.', parts: [{ text: 'It saves water.' }],
    })
    expect(marked([{ text: 'Something else entirely.' }])).toEqual({ label: 'Helps by', text: 'It saves water.' })
  })
})

describe('leadingNumber', () => {
  it('finds the number a value opens with, its decimals and what follows', () => {
    expect(leadingNumber('137,753 ha')).toEqual({ number: 137753, decimals: 0, rest: ' ha' })
    expect(leadingNumber('82.4%')).toEqual({ number: 82.4, decimals: 1, rest: '%' })
    expect(leadingNumber('-12 ha')).toEqual({ number: -12, decimals: 0, rest: ' ha' })
  })

  it('is null for a value that does not open with a number', () => {
    expect(leadingNumber('no figures reported')).toBeNull()
    expect(leadingNumber('A')).toBeNull()
  })
})

describe('labelParts', () => {
  it('splits a label into what is measured and its value', () => {
    expect(labelParts('Surface water irrigation: 600 ha')).toEqual({ name: 'Surface water irrigation', value: '600 ha' })
  })

  it('leaves a sentence whole', () => {
    expect(labelParts('Groundwater irrigates 1,500 ha more than surface water')).toEqual({
      name: null, value: 'Groundwater irrigates 1,500 ha more than surface water',
    })
  })
})
