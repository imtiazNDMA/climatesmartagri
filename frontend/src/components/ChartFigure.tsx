import type { ReactNode } from 'react'
import type { ChartSpec } from '../api/types'
import { BalanceChart } from './BalanceChart'
import { CalendarChart } from './CalendarChart'
import { Chart } from './Chart'
import { OutlookChart } from './OutlookChart'
import { CountsChart, DivergingChart, SharesChart } from './StoryCharts'
import { EfficiencyExplorer, EfficiencyGrid } from './WaterCharts'

/** Draws any chart the backend describes, picking the component for its kind. `switcher` goes above a plain chart's title. */
export function ChartFigure({
  spec, year, large = false, switcher,
}: { spec: ChartSpec; year: number | null; large?: boolean; switcher?: ReactNode }) {
  if (spec.kind === 'calendar') return <CalendarChart spec={spec} large={large} />
  if (spec.kind === 'balance') return <BalanceChart spec={spec} year={year} large={large} />
  if (spec.kind === 'shares') return <SharesChart spec={spec} large={large} />
  if (spec.kind === 'diverging') return <DivergingChart spec={spec} large={large} />
  if (spec.kind === 'counts') return <CountsChart spec={spec} large={large} />
  if (spec.kind === 'outlook') return <OutlookChart spec={spec} year={year} large={large} />
  if (spec.kind === 'explorer') return <EfficiencyExplorer spec={spec} year={year} large={large} />
  if (spec.kind === 'grid') return <EfficiencyGrid spec={spec} year={year} large={large} />
  return <Chart spec={spec} year={year} large={large} switcher={switcher} />
}
