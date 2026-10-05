import { Map as MapIcon } from 'lucide-react'
import type { Place, Section } from '../api/types'
import { formatNumber } from '../charts/chartOption'
import type { SectionDataState } from '../data/useSectionData'
import { viewStore } from '../state/viewState'
import { ChartFigure } from './ChartFigure'

const EMPTY_STATES: Record<string, string> = {
  'no-data': 'Data not loaded yet',
  'coming-soon': 'Coming soon',
  loading: 'Loading…',
  idle: 'Loading…',
}

/** The section's charts at full size, in place of the map: key figures first, then one finding per chart. */
export function ChartsView({
  section,
  place,
  sectionData,
}: {
  section: Section
  place: Place | undefined
  sectionData: SectionDataState
}) {
  const data = sectionData.status === 'ready' ? sectionData.data : null

  return (
    <section className="charts-view" aria-label="Charts in full view">
      <header className="charts-view-header">
        <div>
          <h2>{section.title}</h2>
          <p className="charts-view-where">
            <span>{place?.name ?? 'Pakistan'}</span>
            {data?.year !== null && data?.year !== undefined && <span>, {data.year}</span>}
            {place && place.level !== 'national' && (
              <>
                {' · '}
                <button type="button" className="link-button" onClick={() => viewStore.getState().selectPlace(null)}>
                  Show all of Pakistan
                </button>
              </>
            )}
          </p>
        </div>
        <button type="button" className="charts-view-back" onClick={() => viewStore.getState().setFull(false)}>
          <MapIcon size={16} aria-hidden /> Back to map
        </button>
      </header>

      {!data && (
        <p className="empty">
          {sectionData.status === 'error'
            ? `Charts could not be loaded: ${sectionData.message}`
            : EMPTY_STATES[sectionData.status]}
        </p>
      )}

      {data && data.level_used === 'national' && place && place.level !== 'national' && (
        <p className="national-only">National figures only</p>
      )}

      {data && data.figures.length > 0 && (
        <dl className="charts-view-figures">
          {data.figures.map((figure) => (
            <div key={figure.label}>
              <dt>{figure.label}</dt>
              <dd>
                {figure.value === null
                  ? 'Not reported'
                  : [formatNumber(figure.value), figure.unit].filter((part) => part !== '').join(' ')}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {data && data.charts.length === 0 && <p className="empty">No charts for this selection.</p>}

      {data && data.charts.length > 0 && (
        <div className="charts-view-grid">
          {data.charts.map((chart) => (
            <ChartFigure key={chart.id} spec={chart} year={data.year} large />
          ))}
        </div>
      )}

      {data && (data.notes ?? []).length > 0 && (
        <footer className="charts-view-notes">
          <h3>About these figures</h3>
          {(data.notes ?? []).map((note) => (
            <p key={note}>{note}</p>
          ))}
        </footer>
      )}
    </section>
  )
}
