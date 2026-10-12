import type { ChartSpec } from '../api/types'
import { BalanceChart } from './BalanceChart'
import { CalendarChart } from './CalendarChart'
import { Chart } from './Chart'
import { CountsChart, DivergingChart, SharesChart } from './StoryCharts'

/** Draws any chart the backend describes, picking the component for its kind. */
export function ChartFigure({ spec, year, large = false }: { spec: ChartSpec; year: number | null; large?: boolean }) {
  if (spec.kind === 'calendar') return <CalendarChart spec={spec} large={large} />
  if (spec.kind === 'balance') return <BalanceChart spec={spec} year={year} large={large} />
  if (spec.kind === 'shares') return <SharesChart spec={spec} large={large} />
  if (spec.kind === 'diverging') return <DivergingChart spec={spec} large={large} />
  if (spec.kind === 'counts') return <CountsChart spec={spec} large={large} />
  return <Chart spec={spec} year={year} large={large} />
}
