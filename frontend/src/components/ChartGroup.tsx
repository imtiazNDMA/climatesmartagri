import { useState, type ReactNode } from 'react'
import type { ChartSpec } from '../api/types'

/** The charts as cards: charts of one group share a card, at the place of the first of them. */
export function groupCharts(charts: ChartSpec[]): ChartSpec[][] {
  const cards: ChartSpec[][] = []
  const byGroup = new Map<string, ChartSpec[]>()
  for (const chart of charts) {
    const card = chart.group ? byGroup.get(chart.group) : undefined
    if (card) {
      card.push(chart)
      continue
    }
    const fresh = [chart]
    cards.push(fresh)
    if (chart.group) byGroup.set(chart.group, fresh)
  }
  return cards
}

/** One card's charts with a switch between them, handed to the chart to show above its title; a card of one chart has no switch. */
export function ChartGroup({
  charts,
  initial,
  children,
}: {
  charts: ChartSpec[]
  initial?: string | null
  children: (chart: ChartSpec, switcher: ReactNode) => ReactNode
}) {
  const [pickedId, setPickedId] = useState(initial ?? charts[0].id)
  // A chart that is no longer offered, after a change of year for instance, falls back to the first.
  const picked = charts.find((chart) => chart.id === pickedId) ?? charts[0]
  const switcher = charts.length > 1 && (
    <div className="chart-switch" role="group" aria-label="Compare with">
      {charts.map((chart) => (
        <button key={chart.id} type="button" aria-pressed={chart.id === picked.id} onClick={() => setPickedId(chart.id)}>
          {chart.group_label ?? chart.title}
        </button>
      ))}
    </div>
  )
  return <>{children(picked, switcher)}</>
}
