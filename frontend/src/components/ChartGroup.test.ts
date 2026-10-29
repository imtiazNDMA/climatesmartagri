import { describe, expect, it } from 'vitest'
import type { ChartSpec } from '../api/types'
import { groupCharts } from './ChartGroup'

const chart = (id: string, group?: string): ChartSpec => ({
  id, title: id, kind: 'bar', unit: '', time: false, categories: [], series: [], ...(group ? { group } : {}),
})

describe('groupCharts', () => {
  it('puts the charts of a group on one card, where the first of them stood', () => {
    const cards = groupCharts([chart('a'), chart('since-2022', 'change'), chart('b'), chart('since-2017', 'change')])
    expect(cards.map((card) => card.map((c) => c.id))).toEqual([['a'], ['since-2022', 'since-2017'], ['b']])
  })

  it('gives every chart without a group a card of its own', () => {
    expect(groupCharts([chart('a'), chart('b')])).toHaveLength(2)
  })
})
