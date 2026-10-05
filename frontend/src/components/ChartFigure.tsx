import type { ChartSpec } from '../api/types'
import { CalendarChart } from './CalendarChart'
import { Chart } from './Chart'

/** Draws any chart the backend describes, picking the component for its kind. */
export function ChartFigure({ spec, year, large = false }: { spec: ChartSpec; year: number | null; large?: boolean }) {
  if (spec.kind === 'calendar') return <CalendarChart spec={spec} large={large} />
  return <Chart spec={spec} year={year} large={large} />
}
