import { Expand, Map as MapIcon, Maximize2, Minimize2, Shrink } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { Place, Section } from '../api/types'
import { formatNumber } from '../charts/chartOption'
import type { SectionDataState } from '../data/useSectionData'
import { useView, viewStore } from '../state/viewState'
import { ChartFigure } from './ChartFigure'
import { ChartGroup, groupCharts } from './ChartGroup'

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
  const maximizedId = useView((s) => s.maximized)
  const [fullscreenId, setFullscreenId] = useState<string | null>(null)
  // A chart that is no longer offered, after a change of place for instance, cannot stay maximized.
  const maximized = data?.charts.find((chart) => chart.id === maximizedId) ?? null
  // Charts are shown a card at a time; a maximized chart brings the card it is on.
  const cards = groupCharts(data?.charts ?? [])
  const shown = maximized ? cards.filter((card) => card.includes(maximized)) : cards

  useEffect(() => {
    if (!maximized) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') viewStore.getState().maximize(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [maximized])

  useEffect(() => {
    const syncFullscreen = () => {
      const element = document.fullscreenElement as HTMLElement | null
      setFullscreenId(element?.dataset.chartId ?? null)
    }
    document.addEventListener('fullscreenchange', syncFullscreen)
    return () => document.removeEventListener('fullscreenchange', syncFullscreen)
  }, [])

  const toggleFullscreen = async (element: HTMLDivElement, chartId: string) => {
    if (document.fullscreenElement === element) {
      await document.exitFullscreen()
      return
    }
    if (document.fullscreenElement) await document.exitFullscreen()
    await element.requestFullscreen()
    setFullscreenId(chartId)
  }

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
          {shown.map((card) => (
            <div key={card[0].id} className="chart-cell" data-chart-id={card[0].id}>
              <ChartGroup charts={card} initial={maximized?.id}>
                {(chart, switcher) => (
                  <>
                    <ChartFigure spec={chart} year={data.year} large switcher={switcher} />
                    <div className="chart-actions">
                      {cards.length > 1 && (
                        <button
                          type="button"
                          className="chart-size"
                          title={maximized ? 'Minimize' : 'Maximize'}
                          aria-label={`${maximized ? 'Minimize' : 'Maximize'}: ${chart.title}`}
                          onClick={() => viewStore.getState().maximize(maximized ? null : chart.id)}
                        >
                          {maximized ? <Minimize2 size={18} aria-hidden /> : <Maximize2 size={18} aria-hidden />}
                        </button>
                      )}
                      <button
                        type="button"
                        className="chart-fullscreen"
                        title={fullscreenId === card[0].id ? 'Exit full screen' : 'View chart full screen'}
                        aria-label={`${fullscreenId === card[0].id ? 'Exit full screen' : 'View full screen'}: ${chart.title}`}
                        onClick={(event) => void toggleFullscreen(event.currentTarget.closest<HTMLDivElement>('.chart-cell')!, card[0].id)}
                      >
                        {fullscreenId === card[0].id ? <Shrink size={18} aria-hidden /> : <Expand size={18} aria-hidden />}
                      </button>
                    </div>
                  </>
                )}
              </ChartGroup>
            </div>
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
